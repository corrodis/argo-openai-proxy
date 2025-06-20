import json
import uuid
from http import HTTPStatus
from typing import Any, Dict, Optional, Union

import aiohttp
from aiohttp import web
from loguru import logger

from .chat import (
    prepare_request_data,
    send_non_streaming_request,
    send_streaming_request,
)
from ..config import ArgoConfig
from ..types import Completion, CompletionChoice, CompletionUsage
from ..utils import make_bar

DEFAULT_STREAM = False


def make_it_openai_completions_compat(
    custom_response: Union[str, Dict[str, Any]],
    model_name: str,
    create_timestamp: int,
    prompt_tokens: int,
    is_streaming: bool = False,
    finish_reason: Optional[str] = None,
) -> Union[Dict[str, Any], str]:
    """Converts a custom API response to an OpenAI-compatible completion API response.

    Args:
        custom_response (Union[str, Dict[str, Any]]): The custom API response in JSON format.
        model_name (str): The model name used for generating the completion.
        create_timestamp (int): Timestamp indicating when the completion was created.
        prompt_tokens (int): Number of tokens in the input prompt.
        is_streaming (bool, optional): Indicates if the response is in streaming mode. Defaults to False.
        finish_reason (str, optional): Reason for the completion stop. Defaults to None.

    Returns:
        Union[Dict[str, Any], str]: OpenAI-compatible JSON response or an error message.
    """
    try:
        # Parse the custom response
        if isinstance(custom_response, str):
            custom_response_dict = json.loads(custom_response)
        else:
            custom_response_dict = custom_response

        # Extract the response text
        response_text: str = custom_response_dict.get("response", "")

        # Calculate token counts (simplified example, actual tokenization may differ)
        if not is_streaming:
            completion_tokens: int = len(response_text.split())
            total_tokens: int = prompt_tokens + completion_tokens
            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

        openai_response = Completion(
            id=f"cmpl-{uuid.uuid4().hex}",
            created=create_timestamp,
            model=model_name,
            choices=[
                CompletionChoice(
                    text=response_text,
                    index=0,
                    finish_reason=finish_reason or "stop",
                )
            ],
            usage=usage
            if not is_streaming
            else None,  # Usage is not provided in streaming mode
        )

        return openai_response.model_dump()

    except json.JSONDecodeError as err:
        return {"error": f"Error decoding JSON: {err}"}
    except Exception as err:
        return {"error": f"An error occurred: {err}"}


async def proxy_request(
    request: web.Request,
) -> Union[web.Response, web.StreamResponse]:
    """Proxies incoming requests to the upstream API and processes responses.

    Args:
        request (web.Request): The incoming HTTP request object.
        convert_to_openai (bool, optional): Whether to convert the response to OpenAI-compatible format. Defaults to False.

    Returns:
        web.Response or web.StreamResponse: The HTTP response sent back to the client.

    Raises:
        ValueError: Raised when the request data is invalid or missing.
        aiohttp.ClientError: Raised when there is an HTTP client error.
        Exception: Raised for unexpected runtime errors.
    """
    config: ArgoConfig = request.app["config"]
    try:
        # Retrieve the incoming JSON data
        data: Dict[str, Any] = await request.json()
        stream: bool = data.get("stream", DEFAULT_STREAM)

        if not data:
            raise ValueError("Invalid input. Expected JSON data.")
        if config.verbose:
            logger.info(make_bar("[completion] input"))
            logger.info(json.dumps(data, indent=4))
            logger.info(make_bar())

        # Prepare the request data
        data = prepare_request_data(data, request)

        # Determine the API URL based on whether streaming is enabled
        api_url: str = config.argo_stream_url if stream else config.argo_url

        # Forward the modified request to the actual API using aiohttp
        async with aiohttp.ClientSession() as session:
            if stream:
                return await send_streaming_request(
                    session,
                    api_url,
                    data,
                    request,
                    convert_to_openai=True,
                    openai_compat_fn=make_it_openai_completions_compat,
                )
            else:
                return await send_non_streaming_request(
                    session,
                    api_url,
                    data,
                    convert_to_openai=True,
                    openai_compat_fn=make_it_openai_completions_compat,
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
