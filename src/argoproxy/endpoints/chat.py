import asyncio
import json
import time
import uuid
from http import HTTPStatus
from typing import Any, Callable, Dict, Optional, Union
import re
import json

import aiohttp
from aiohttp import web
from loguru import logger

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..types import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    ChoiceDelta,
    CompletionUsage,
    NonStreamChoice,
    StreamChoice,
)
from ..types.chat_completion import FINISH_REASONS
from ..utils.input_handle import (
    handle_multiple_entries_prompt,
    handle_no_sys_msg,
    handle_non_stream_only,
    # handle_option_2_input,
)
from ..utils.misc import make_bar
from ..utils.tokens import calculate_prompt_tokens, count_tokens
from ..utils.transports import send_off_sse

DEFAULT_MODEL = "argo:gpt-4o"


def make_it_openai_chat_completions_compat(
    custom_response: Any,
    model_name: str,
    create_timestamp: int,
    prompt_tokens: int,
    is_streaming: bool = False,
    finish_reason: Optional[FINISH_REASONS] = None,
    translate_tools: Optional[bool] = False
) -> Dict[str, Any]:
    """
    Transforms the custom API response into a format compatible with OpenAI's API.

    Args:
        custom_response: The response obtained from the custom API.
        model_name: The name of the model that generated the completion.
        create_timestamp: The creation timestamp of the completion.
        prompt_tokens: The number of tokens in the input prompt.
        is_streaming: Boolean indicating if the response is streaming.
        finish_reason: The reason for response completion, e.g., "stop".

    Returns:
        A dictionary representing the OpenAI-compatible JSON response.
    """
    try:
        # Parse the custom response
        if isinstance(custom_response, str):
            custom_response_dict = json.loads(custom_response)
        else:
            custom_response_dict = custom_response

        # Extract the response text
        response_text = custom_response_dict.get("response", "")

        usage = None
        if not is_streaming:
            # only count usage if not stream
            # Calculate token counts (simplified example, actual tokenization may differ)
            completion_tokens = count_tokens(response_text, model_name)
            total_tokens = prompt_tokens + completion_tokens
            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

        if is_streaming:
            openai_response = ChatCompletionChunk(
                id=str(uuid.uuid4().hex),
                created=create_timestamp,
                model=model_name,
                choices=[
                    StreamChoice(
                        index=0,
                        delta=ChoiceDelta(
                            content=response_text,
                        ),
                        finish_reason=finish_reason or "stop",
                    )
                ],
            )
        else:
            openai_response = ChatCompletion(
                id=str(uuid.uuid4().hex),
                created=create_timestamp,
                model=model_name,
                choices=[
                    NonStreamChoice(
                        index=0,
                        message=ChatCompletionMessage(
                            content=response_text,
                        ),
                        finish_reason=finish_reason or "stop",
                    )
                ],
                usage=usage,
            )
        
        response_dict = openai_response.model_dump()
        if translate_tools:
            response_dict = _translate_to_function_call_if_needed(response_dict, response_text, is_streaming)

        return response_dict

    except json.JSONDecodeError as err:
        return {"error": f"Error decoding JSON: {err}"}
    except Exception as err:
        return {"error": f"An error occurred: {err}"}


def prepare_chat_request_data(
    data: Dict[str, Any], config: ArgoConfig, model_registry: ModelRegistry
) -> Dict[str, Any]:
    """
    Prepares chat request data for upstream APIs based on model type.

    Args:
        data: The incoming request data.
        config: The ArgoConfig object containing configuration settings.
        model_registry: The ModelRegistry object containing model mappings.

    Returns:
        The modified request data.
    """
    # Automatically replace or insert user information
    data["user"] = config.user

    # Remap the model name
    if "model" not in data:
        data["model"] = DEFAULT_MODEL
    data["model"] = model_registry.resolve_model_name(data["model"], model_type="chat")

    # Convert prompt to list if necessary
    if "prompt" in data and not isinstance(data["prompt"], list):
        data["prompt"] = [data["prompt"]]

    if getattr(config, 'translate_tools', False):
        if "tools" in data:
            for msg in data['messages']:
                if msg['role'] == 'system':
                    msg['content'] =  _build_function_calling_prompt(data["tools"]) + msg['content']
                    msg["tools"] = None
            data['tools'] = None

    # # Apply transformations based on model type
    # if data["model"] in model_registry.option_2_input_models:
    #     # Transform data for models requiring `system` and `prompt` structure only
    #     data = handle_option_2_input(data)

    # flatten the list of strings into a single string in case of multiple prompts
    if isinstance(data.get("prompt"), list):
        data["prompt"] = ["\n\n".join(data["prompt"]).strip()]

    if data["model"] in model_registry.no_sys_msg_models:
        data = handle_no_sys_msg(data)

    if data["model"] not in model_registry.streamable_models:
        data = handle_non_stream_only(data)

    data = handle_multiple_entries_prompt(data)

    # if config.verbose:
    #     logger.info(make_bar("Transformed Request"))
    #     logger.info(f"{json.dumps(data, indent=2)}")

    return data

def _schema_to_prompt(tools):
    prompt_parts = ["Available functions:"]
    
    for tool in tools:
        func = tool["function"]
        name = func["name"]
        description = func["description"]
        
        # Parse parameters
        params = []
        if "parameters" in func and "properties" in func["parameters"]:
            for param_name, param_info in func["parameters"]["properties"].items():
                param_type = param_info.get("type", "string")
                param_desc = param_info.get("description", "")
                required = param_name in func["parameters"].get("required", [])
                
                param_str = f"{param_name}: {param_type}"
                if required:
                    param_str += " (required)"
                if param_desc:
                    param_str += f" - {param_desc}"
                params.append(param_str)
        
        func_signature = f"- {name}({', '.join(params)}): {description}"
        prompt_parts.append(func_signature)
    
    return "\n".join(prompt_parts)

def _build_function_calling_prompt(tools):
    function_descriptions = _schema_to_prompt(tools)
    
    prompt = f"""You are a helpful assistant with access to functions. When you want to call a function, use the exact format below in your response to the user:

When an interaction requires a function call, respond IMMEDIATELY and ONLY with:
FUNCTION_CALL: function_name
ARGUMENTS: {{"param1": "value1", "param2": "value2"}}

NEVER say "I will", "Let me", "I'll retrieve", or any explanatory text.

Example:
    User: "What is the summary of document ABC?"
    Correct response: FUNCTION_CALL: get\nARGUMENTS: {{"docid": "ABC"}}
    Wrong response: "I will retrieve the content for you."

Just call the function immediately using the exact format above. The ARGUMENTS must be valid JSON. Use double quotes for string.

Otherwise, respond normally with text.

{function_descriptions}"""
    
    return prompt

def _parse_function_call_response(response_text):
    """
    Parse function call format:
    FUNCTION_CALL: function_name
    ARGUMENTS: {"param": "value"}
    
    Returns:
        tuple: (is_function_call: bool, function_name: str, arguments: dict)
    """
    
    # Look for the pattern
    pattern = r'FUNCTION_CALL:\s*(\w+)\s*\nARGUMENTS:\s*(\{.*?\})'
    match = re.search(pattern, response_text, re.DOTALL)
    
    if match:
        function_name = match.group(1).strip()
        arguments_str = match.group(2).strip()
        
        try:
            arguments = json.loads(arguments_str)
            return True, function_name, arguments
        except json.JSONDecodeError:
            # If JSON is malformed, return as regular text
            return False, None, None
    
    return False, None, None

def _translate_to_function_call_if_needed(response_dict: Dict[str, Any], response_text: str, is_streaming: bool) -> Dict[str, Any]:
    is_function_call, function_name, arguments = _parse_function_call_response(response_text)

    if is_function_call:
        tool_calls = [{
            'id': f'call_{uuid.uuid4().hex[:10]}',
            'type': 'function',
            'function': {
                'name': function_name,
                'arguments': json.dumps(arguments)
             }
        }]
       
        if is_streaming:
            response_dict['choices'][0]['delta'] = {'tool_calls': tool_calls}
        else:
            response_dict['choices'][0]['message'] = {
                'content': None,
                'tool_calls': tool_calls
            }
	
        response_dict['choices'][0]['finish_reason'] = 'tool_calls' 
    
    return response_dict

async def send_non_streaming_request(
    session: aiohttp.ClientSession,
    api_url: str,
    data: Dict[str, Any],
    convert_to_openai: bool = False,
    translate_tools: bool = False,
    openai_compat_fn: Callable[
        ..., Dict[str, Any]
    ] = make_it_openai_chat_completions_compat,
) -> web.Response:
    """Sends a non-streaming request to an API and processes the response.

    Args:
        session: The client session for making the request.
        api_url: URL of the API endpoint.
        data: The JSON payload of the request.
        convert_to_openai: If True, converts the response to OpenAI format.
        openai_compat_fn: Function for conversion to OpenAI-compatible format.

    Returns:
        A web.Response with the processed JSON data.
    """
    headers = {"Content-Type": "application/json"}
    async with session.post(api_url, headers=headers, json=data) as upstream_resp:
        response_data = await upstream_resp.json()
        upstream_resp.raise_for_status()

        if convert_to_openai:
            # Calculate prompt tokens using the unified function
            prompt_tokens = calculate_prompt_tokens(data, data["model"])
            openai_response = openai_compat_fn(
                json.dumps(response_data),
                model_name=data.get("model"),
                create_timestamp=int(time.time()),
                prompt_tokens=prompt_tokens,
                translate_tools=translate_tools,
            )
            return web.json_response(
                openai_response,
                status=upstream_resp.status,
                content_type="application/json",
            )
        else:
            return web.json_response(
                response_data,
                status=upstream_resp.status,
                content_type="application/json",
            )


async def send_streaming_request(
    session: aiohttp.ClientSession,
    api_url: str,
    data: Dict[str, Any],
    request: web.Request,
    convert_to_openai: bool = False,
    translate_tools: bool = False,
    *,
    openai_compat_fn: Callable[
        ..., Dict[str, Any]
    ] = make_it_openai_chat_completions_compat,
    fake_stream: bool = False,
) -> web.StreamResponse:
    """Sends a streaming request to an API and streams the response to the client.

    Args:
        session: The client session for making the request.
        api_url: URL of the API endpoint.
        data: The JSON payload of the request.
        request: The web request used for streaming responses.
        convert_to_openai: If True, converts the response to OpenAI format.
        openai_compat_fn: Function for conversion to OpenAI-compatible format.
        fake_stream: If True, simulates streaming by sending the response in chunks.
    """

    async def handle_chunk(chunk, finish_reason=None):
        """
        Handles a chunk of data, converting it if necessary and sending it off.
        """
        if convert_to_openai:
            # Convert the chunk to OpenAI-compatible JSON
            chunk_json = openai_compat_fn(
                json.dumps({"response": chunk.decode()}),
                model_name=data["model"],
                create_timestamp=created_timestamp,
                prompt_tokens=prompt_tokens,
                is_streaming=True,
                finish_reason=finish_reason,  # May be None for ongoing chunks
            )
            await send_off_sse(response, chunk_json)
        else:
            # Return the chunk as raw text
            await send_off_sse(response, chunk)

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/plain",
        "Accept-Encoding": "identity",
    }

    # Set response headers based on the mode
    if convert_to_openai:
        response_headers = {"Content-Type": "text/event-stream"}
        created_timestamp = int(time.time())
        prompt_tokens = calculate_prompt_tokens(data, data["model"])
    else:
        response_headers = {"Content-Type": "text/plain; charset=utf-8"}

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
                not in (
                    "content-type",
                    "content-encoding",
                    "transfer-encoding",
                    "content-length",  # in case of fake streaming
                )
            }
        )
        response = web.StreamResponse(
            status=upstream_resp.status,
            headers=response_headers,
        )

        response.enable_chunked_encoding()
        await response.prepare(request)

        if fake_stream:
            # Get full response first
            response_data = await upstream_resp.json()
            response_text = response_data.get("response", "")

            # Split into chunks of ~10 characters to simulate streaming
            chunk_size = 20
            for i in range(0, len(response_text), chunk_size):
                chunk = response_text[i : i + chunk_size]
                finish_reason = None if i + chunk_size < len(response_text) else "stop"
                await handle_chunk(chunk.encode(), finish_reason)
                await asyncio.sleep(0.02)  # Small delay between chunks
        else:
            chunk_iterator = upstream_resp.content.iter_any()
            async for chunk in chunk_iterator:
                await handle_chunk(chunk)

        # Ensure response is properly closed
        await response.write_eof()

        return response


async def proxy_request(
    request: web.Request,
    *,
    convert_to_openai: bool = True,
) -> Union[web.Response, web.StreamResponse]:
    """Proxies the client's request to an upstream API, handling response streaming and conversion.

    Args:
        request: The client's web request object.
        convert_to_openai: If True, translates the response to an OpenAI-compatible format.

    Returns:
        A web.Response or web.StreamResponse with the final response from the upstream API.
    """
    config: ArgoConfig = request.app["config"]
    model_registry: ModelRegistry = request.app["model_registry"]

    try:
        # Retrieve the incoming JSON data from request if input_data is not provided

        data = await request.json()
        stream = data.get("stream", False)

        if not data:
            raise ValueError("Invalid input. Expected JSON data.")
        if config.verbose:
            logger.info(make_bar("[chat] input"))
            logger.info(json.dumps(data, indent=4))
            logger.info(make_bar())

        # Prepare the request data
        data = prepare_chat_request_data(data, config, model_registry)
        # this is the stream flag sent to upstream API
        upstream_stream = data.get("stream", False)

        # Determine the API URL based on whether streaming is enabled 
        api_url = config.argo_stream_url if upstream_stream else config.argo_url
        # 
        translate_tools = getattr(config,"translate_tools",False)

        # Forward the modified request to the actual API using aiohttp
        async with aiohttp.ClientSession() as session:
            if stream:
                return await send_streaming_request(
                    session,
                    api_url,
                    data,
                    request,
                    convert_to_openai,
                    translate_tools,
                    fake_stream=(stream != upstream_stream),
                )
            else:
                return await send_non_streaming_request(
                    session,
                    api_url,
                    data,
                    convert_to_openai,
                    translate_tools
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
