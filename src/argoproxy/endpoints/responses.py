import fnmatch
import json
import time
import uuid
from http import HTTPStatus
from typing import Any, Dict, Union

import aiohttp
from aiohttp import web
from loguru import logger

from ..config import ArgoConfig
from ..constants import CHAT_MODELS
from ..types import (
    Response,
    ResponseCompletedEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreatedEvent,
    ResponseInProgressEvent,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
    ResponseUsage,
)
from ..utils import (
    calculate_prompt_tokens,
    count_tokens,
    make_bar,
    resolve_model_name,
    send_off_sse,
)
from .chat import send_non_streaming_request

DEFAULT_MODEL = "gpt4o"

NO_SYS_MSG_PATTERNS = {
    "^argo:gpt-o.*$",
    "^argo:o.*$",
    "^gpto.*$",
}

NO_SYS_MSG = [
    model
    for model in CHAT_MODELS
    if any(fnmatch.fnmatch(model, pattern) for pattern in NO_SYS_MSG_PATTERNS)
]

INCOMPATIBLE_INPUT_FIELDS = {
    "include",
    "metadata",
    "parallel_tool_calls",
    "previous_response_id",
    "reasoning",
    "service_tier",
    "store",
    "text",
    "tool_choice",
    "tools",
    "truncation",
}


def transform_non_streaming_response(
    custom_response: Any,
    model_name: str,
    create_timestamp: int,
    prompt_tokens: int,
    **kwargs,
) -> Dict[str, Any]:
    """
    Transforms a non-streaming custom API response into a format compatible with OpenAI's API.

    Args:
        custom_response: The response obtained from the custom API.
        model_name: The name of the model that generated the completion.
        create_timestamp: The creation timestamp of the completion.
        prompt_tokens: The number of tokens in the input prompt.

    Returns:
        A dictionary representing the OpenAI-compatible JSON response.
    """
    try:
        if isinstance(custom_response, str):
            custom_response_dict = json.loads(custom_response)
        else:
            custom_response_dict = custom_response

        response_text = custom_response_dict.get("response", "")
        completion_tokens = count_tokens(response_text, model_name)
        total_tokens = prompt_tokens + completion_tokens
        usage = ResponseUsage(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

        id = str(uuid.uuid4().hex)
        openai_response = Response(
            id=f"resp_{id}",
            created_at=create_timestamp,
            model=model_name,
            output=[
                ResponseOutputMessage(
                    id=f"msg_{id}",
                    status="completed",
                    content=[
                        ResponseOutputText(
                            text=response_text,
                        )
                    ],
                )
            ],
            status="completed",
            usage=usage,
        )

        return openai_response.model_dump()

    except json.JSONDecodeError as err:
        logger.error(f"Error decoding JSON: {err}")
        return {"error": f"Error decoding JSON: {err}"}
    except Exception as err:
        logger.error(f"An error occurred: {err}")
        return {"error": f"An error occurred: {err}"}


def transform_streaming_response(
    custom_response: Any,
    **kwargs,
) -> Dict[str, Any]:
    """
    Transforms a streaming custom API response into a format compatible with OpenAI's API.

    Args:
        custom_response: The response obtained from the custom API.
        model_name: The name of the model that generated the completion.

    Returns:
        A dictionary representing the OpenAI-compatible JSON response.
    """
    try:
        if isinstance(custom_response, str):
            custom_response_dict = json.loads(custom_response)
        else:
            custom_response_dict = custom_response

        response_text = custom_response_dict.get("response", "")
        content_index = kwargs.get("content_index", 0)
        output_index = kwargs.get("output_index", 0)
        sequence_number = kwargs.get("sequence_number", 0)
        id = kwargs.get("id", f"msg_{str(uuid.uuid4().hex)}")

        openai_response = ResponseTextDeltaEvent(
            content_index=content_index,
            delta=response_text,
            item_id=id,
            output_index=output_index,
            sequence_number=sequence_number,
        )

        return openai_response.model_dump()

    except json.JSONDecodeError as err:
        logger.error(f"Error decoding JSON: {err}")
        return {"error": f"Error decoding JSON: {err}"}
    except Exception as err:
        logger.error(f"An error occurred: {err}")
        return {"error": f"An error occurred: {err}"}


def prepare_request_data(
    data: Dict[str, Any],
    request: web.Request,
) -> Dict[str, Any]:
    """
    Modifies and prepares the incoming request data by adding user information
    and remapping the model according to configurations.

    Args:
        data: The original request data.
        request: The incoming web request object.

    Returns:
        The modified and prepared request data.
    """
    config: ArgoConfig = request.app["config"]
    # Automatically replace or insert the user
    data["user"] = config.user

    # Remap the model using MODEL_AVAIL
    if "model" in data:
        data["model"] = resolve_model_name(
            data["model"], DEFAULT_MODEL, avail_models=CHAT_MODELS
        )
    else:
        data["model"] = DEFAULT_MODEL

    # obtain messages from input
    messages = data.get("input", [])
    # Insert instructions as a system message
    if instructions := data.get("instructions", ""):
        messages.insert(0, {"role": "system", "content": instructions})
        del data["instructions"]
    # replace input with messages
    data["messages"] = messages
    del data["input"]

    if max_tokens := data.get("max_output_tokens", None):
        data["max_tokens"] = max_tokens
        del data["max_output_tokens"]

    # Convert system message to user message for specific models
    if data["model"] in NO_SYS_MSG:
        if "messages" in data:
            for message in data["messages"]:
                if message["role"] == "system":
                    message["role"] = "user"

    # drop other unsupported fields
    for key in list(data.keys()):
        if key in INCOMPATIBLE_INPUT_FIELDS:
            del data[key]
    return data


async def send_streaming_request(
    session: aiohttp.ClientSession,
    api_url: str,
    data: Dict[str, Any],
    request: web.Request,
) -> web.StreamResponse:
    """Sends a streaming request to an API and streams the response to the client.

    Args:
        session: The client session for making the request.
        api_url: URL of the API endpoint.
        data: The JSON payload of the request.
        request: The web request used for streaming responses.
        convert_to_openai: If True, converts the response to OpenAI format.
        openai_compat_fn: Function for conversion to OpenAI-compatible format.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/plain",
        "Accept-Encoding": "identity",
    }

    # Set response headers based on the mode
    response_headers = {"Content-Type": "text/event-stream"}
    created_timestamp = int(time.time())
    prompt_tokens = calculate_prompt_tokens(data, data["model"])

    async with session.post(api_url, headers=headers, json=data) as upstream_resp:
        if upstream_resp.status != 200:
            # Read error content from upstream response
            error_text = await upstream_resp.text()
            # Return JSON error response to client
            return web.json_response(
                {"error": f"Upstream API error: {upstream_resp.status} {error_text}"},
                status=upstream_resp.status,
                content_type="application/json",
            )

        # Initialize the streaming response
        response_headers.update(
            {
                k: v
                for k, v in upstream_resp.headers.items()
                if k.lower()
                not in ("Content-Type", "content-encoding", "transfer-encoding")
            }
        )
        response = web.StreamResponse(
            status=upstream_resp.status,
            headers=response_headers,
        )
        response.enable_chunked_encoding()
        await response.prepare(request)

        # =======================================
        # Start event flow with ResponseCreatedEvent
        sequence_number = 0
        id = str(uuid.uuid4().hex)  # Generate a unique ID for the response

        onset_response = Response(
            id=f"resp_{id}",
            created_at=created_timestamp,
            model=data["model"],
            output=[],
            status="in_progress",
        )
        created_event = ResponseCreatedEvent(
            response=onset_response,
            sequence_number=sequence_number,
        )
        await send_off_sse(response, created_event.model_dump())

        # =======================================
        # ResponseInProgressEvent, start streaming the response
        sequence_number += 1
        in_progress_event = ResponseInProgressEvent(
            response=onset_response,
            sequence_number=sequence_number,
        )
        await send_off_sse(response, in_progress_event.model_dump())

        # =======================================
        # ResponseOutputItemAddedEvent, add the output item
        sequence_number += 1
        output_msg = ResponseOutputMessage(
            id=f"msg_{id}",
            content=[],
            status="in_progress",
        )
        output_item = ResponseOutputItemAddedEvent(
            item=output_msg,
            output_index=0,
            sequence_number=sequence_number,
        )
        await send_off_sse(response, output_item.model_dump())

        # =======================================
        # ResponseContentPartAddedEvent, add the content part
        sequence_number += 1
        content_index = 0
        content_part = ResponseContentPartAddedEvent(
            content_index=content_index,
            item_id=output_msg.id,
            output_index=output_item.output_index,
            part=ResponseOutputText(text=""),
            sequence_number=sequence_number,
        )
        await send_off_sse(response, content_part.model_dump())

        # =======================================
        # ResponseTextDeltaEvent, stream the response chunk by chunk
        cumulated_response = ""
        async for chunk in upstream_resp.content.iter_any():
            sequence_number += 1
            chunk_text = chunk.decode()
            cumulated_response += chunk_text  # for ResponseTextDoneEvent

            # Convert the chunk to OpenAI-compatible JSON
            text_delta = transform_streaming_response(
                json.dumps({"response": chunk_text}),
                content_index=content_part.content_index,
                output_index=output_item.output_index,
                sequence_number=sequence_number,
                id=output_msg.id,
            )
            # Wrap the JSON in SSE format
            await send_off_sse(response, text_delta)

        # =======================================
        # ResponseTextDoneEvent, signal the end of the text stream
        sequence_number += 1
        text_done = ResponseTextDoneEvent(
            content_index=content_part.content_index,
            item_id=output_msg.id,
            output_index=output_item.output_index,
            sequence_number=sequence_number,
            text=cumulated_response,  # Use the cumulated response tex
        )
        await send_off_sse(response, text_done.model_dump())

        # =======================================
        # ResponseContentPartDoneEvent, signal the end of the content part
        sequence_number += 1
        output_text = ResponseOutputText(text=cumulated_response)
        content_part_done = ResponseContentPartDoneEvent(
            content_index=content_part.content_index,
            item_id=output_msg.id,
            output_index=output_item.output_index,
            part=output_text,
            sequence_number=sequence_number,
        )
        await send_off_sse(response, content_part_done.model_dump())

        # =======================================
        # ResponseOutputItemDoneEvent, signal the end of the output item
        sequence_number += 1
        output_msg.content = [output_text]
        output_msg.status = "completed"

        output_item_done = ResponseOutputItemDoneEvent(
            item=output_msg,
            output_index=output_item.output_index,
            sequence_number=sequence_number,
        )
        await send_off_sse(response, output_item_done.model_dump())

        # =======================================
        # ResponseCompletedEvent, signal the end of the response
        sequence_number += 1
        onset_response.output.append(output_msg)
        onset_response.status = "completed"
        output_tokens = count_tokens(cumulated_response, data["model"])
        onset_response.usage = ResponseUsage(
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            total_tokens=prompt_tokens + output_tokens,
        )
        completed_event = ResponseCompletedEvent(
            response=onset_response,
            sequence_number=sequence_number,
        )
        await send_off_sse(response, completed_event.model_dump())

        # =======================================
        # Ensure response is properly closed

        await response.write_eof()

        return response


async def proxy_request(
    request: web.Request,
) -> Union[web.Response, web.StreamResponse]:
    """Proxies the client's request to an upstream API, handling response streaming and conversion.

    Args:
        request: The client's web request object.
        convert_to_openai: If True, translates the response to an OpenAI-compatible format.

    Returns:
        A web.Response or web.StreamResponse with the final response from the upstream API.
    """
    config: ArgoConfig = request.app["config"]

    try:
        # Retrieve the incoming JSON data from request if input_data is not provided

        data = await request.json()
        stream = data.get("stream", False)

        if not data:
            raise ValueError("Invalid input. Expected JSON data.")
        if config.verbose:
            logger.info(make_bar("[response] input"))
            logger.info(json.dumps(data, indent=4))
            logger.info(make_bar())

        # Prepare the request data
        data = prepare_request_data(data, request)

        # Determine the API URL based on whether streaming is enabled
        api_url = config.argo_stream_url if stream else config.argo_url

        # Forward the modified request to the actual API using aiohttp
        async with aiohttp.ClientSession() as session:
            if stream:
                return await send_streaming_request(
                    session,
                    api_url,
                    data,
                    request,
                )
            else:
                return await send_non_streaming_request(
                    session,
                    api_url,
                    data,
                    convert_to_openai=True,
                    openai_compat_fn=transform_non_streaming_response,
                )

    except ValueError as err:
        return web.json_response(
            {"error": str(err)},
            status=HTTPStatus.BAD_REQUEST,
            content_type="application/json",
        )
    except aiohttp.ClientError as err:
        error_message = f"HTTP error occurred: {err}"
        return web.json_response(
            {"error": error_message},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type="application/json",
        )
    except Exception as err:
        error_message = f"An unexpected error occurred: {err}"
        return web.json_response(
            {"error": error_message},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            content_type="application/json",
        )
