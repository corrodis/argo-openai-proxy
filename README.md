# argo-openai-proxy

This project is a proxy application that forwards requests to an ARGO API and optionally converts the responses to be compatible with OpenAI's API format. It can be used in conjunction with [autossh-tunnel-dockerized](https://github.com/Oaklight/autossh-tunnel-dockerized) or other secure connection tools.

## NOTICE OF USAGE

The machine or server making the API calls to Argo must be connected to Argonne internal network or through VPN on an Argonne-managed computer if you are working off-site. Meaning your instance of argo proxy should always be on premise at some Argonne Machine.
The software is provided as is, without any warranties or guarantees of any kind, either express or implied. By using this software, you agree that the authors, contributors, and any affiliated organizations shall not be held liable for any damages, losses, or issues arising from its use. This includes, but is not limited to, direct, indirect, incidental, consequential, or punitive damages. You are solely responsible for ensuring that the software meets your requirements and for any outcomes resulting from its use.

To make it easy for you to get started with GitLab, here's a list of recommended next steps.

- [Overview](#argo-proxy-project)
- [Notice of Usage](#notice-of-usage)
- [Folder Structure](#folder-structure)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
  - [Configuration Options](#configuration-options)
  - [Example `config.yaml`](#example-configyaml)
- [Running the Application](#running-the-application)
- [Endpoints](#endpoints)
  - [Timeout Override](#timeout-override)
- [Models](#models)
  - [Chat Models](#chat-models)
  - [Embedding Models](#embedding-models)
- [Examples](#examples)
  - [Chat Completion Example](#chat-completion-example)
  - [Embedding Example](#embedding-example)
  - [o1 Chat Example](#o1-chat-example)
  - [OpenAI Client Example](#openai-client-example)
- [Bug Reports and Contributions](#bug-reports-and-contributions)

## Folder Structure

The following is an overview of the project's directory structure:

```

$ tree .
.
├── app.py
├── argoproxy
│   ├── chat.py
│   ├── completions.py
│   ├── config.py
│   ├── embed.py
│   ├── extras.py
│   └── utils.py
├── config.yaml
├── examples
│   ├── chat_completions_example.py
│   ├── chat_completions_example_stream.py
│   ├── chat_example.py
│   ├── chat_example_stream.py
│   ├── completions_example.py
│   ├── completions_example_stream.py
│   ├── embedding_example.py
│   ├── o1_chat_example.py
│   ├── o3_chat_example_pyclient.py
│   ├── openai_chat_completions_example_stream.py
│   ├── openai_completions_example_stream.py
│   └── results_compare
│       ├── argo_chunk
│       ├── chat_completions
│       │   ├── my_chunk
│       │   ├── openai_chunk
│       │   └── siliconflow_chunk
│       ├── completions
│       │   ├── my_chunk
│       │   ├── openai_chunk
│       │   └── siliconflow_chunk
│       └── my_chunk
├── LICENSE
├── README.md
├── requirements.txt
├── run_app.sh
└── test
    ├── test2.py
    ├── test2.sh
    ├── test.py
    └── test.sh

```

## Prerequisites

- Python 3.10 or higher is required.

## Configuration

The application is configured using a `config.yaml` file. This file contains settings like the ARGO API URLs, port number, and logging behavior.

### Configuration Options

- **`port`**: Port number the application listens to. Default is `44497`.
- **`argo_url`**: URL of the ARGO API for chat/completions. Default: `"https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/"`.
- **`argo_stream_url`**: URL for stream chat/completions. Default: `"https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/steamchat/"`.
- **`argo_embedding_url`**: URL for embeddings. Default: `"https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/embed/"`.
- **`user`**: Username for requests. Default: `"cels"`.
- **`verbose`**: Flag for debugging. Default: `true`.
- **`num_workers`**: Number of worker processes for Gunicorn. Default: `5`.
- **`timeout`**: Default request timeout in seconds. Default: `600`. This value can be overridden by providing a `timeout` parameter in the request or via the OpenAI client.

### Example `config.yaml`

```yaml
# use production url as much as you can.
port: 44497
argo_url: "https://apps.inside.anl.gov/argoapi/api/v1/resource/chat/"
argo_stream_url: "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/streamchat/"
argo_embedding_url: "https://apps.inside.anl.gov/argoapi/api/v1/resource/embed/"
user: "cels" # you should replace it with your username
verbose: true
num_workers: 5
timeout: 600 # in seconds
```

## Integrate with your tools

1. **Install Dependencies**:
   Ensure Python 3.10 or higher is installed. Install required packages using pip:

   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Application**:
   Use `run_app.sh` to start. It defaults to `config.yaml` in the current directory or specify a custom config:

   ```bash
   ./run_app.sh /path/to/config.yaml
   ```

   Without a path, it uses the default `config.yaml`:

   ```bash
   ./run_app.sh
   ```

## Endpoints

The application offers the following endpoints:

- **`/v1/chat`**: Proxies requests to the ARGO API.
- **`/v1/chat/completions`**: Converts ARGO responses to OpenAI-compatible format.
- **`/v1/completions`**: Legacy API for response conversion.
- **`/v1/embeddings`**: Access ARGO Embedding API.
- **`/v1/models`**: Lists available models in OpenAI-compatible format.
- **`/v1/status`**: Responds with a simple "hello" from GPT-4o.

### Timeout Override

Override the default timeout with a `timeout` parameter in your request:

When using the OpenAI client, you can specify a timeout in seconds:

```python
response = client.chat.completions.create(
    model="argo:gpt-4",
    messages=[{"role": "user", "content": "Hello!"}],
    timeout=300
)
```

To specify a timeout using the `requests` library, you can use the `timeout` parameter in your request call:

```python
import requests

url = "http://localhost:44497/v1/chat/completions"
payload = {
    "model": "argo:gpt-4o",
    "messages": [{"role": "user", "content": "Hello!"}],
}
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer whatever+random"
}

response = requests.post(url, json=payload, headers=headers, timeout=300)
print(response.json())
```

For a `curl` command, you can use the `--max-time` option to specify the timeout in seconds. Here's the example:

```bash
curl -X POST http://localhost:44497/v1/chat/completions \
     -H 'Content-Type: application/json' \
     -H 'Authorization: Bearer whatever+random' \
     -d '{"model": "argo:gpt-4o", "messages": [{"role": "user", "content": "Hello!"}]}' \
     --max-time 300
```

## Models

### Chat Models

| Original ARGO Model Name | Argo Proxy Name            |
| ------------------------ | -------------------------- |
| `gpt35`                  | `argo:gpt-3.5-turbo`       |
| `gpt35large`             | `argo:gpt-3.5-turbo-16k`   |
| `gpt4`                   | `argo:gpt-4`               |
| `gpt4large`              | `argo:gpt-4-32k`           |
| `gpt4turbo`              | `argo:gpt-4-turbo-preview` |
| `gpt4o`                  | `argo:gpt-4o`              |
| `gpto1preview`           | `argo:gpt-o1-preview`      |
| `gpto1mini`              | `argo:gpt-o1-mini`         |
| `gpto3mini`              | `argo:gpt-o3-mini`         |

### Embedding Models

| Original ARGO Model Name | Argo Proxy Name               |
| ------------------------ | ----------------------------- |
| `ada002`                 | `argo:text-embedding-ada-002` |
| `v3small`                | `argo:text-embedding-3-small` |
| `v3large`                | `argo:text-embedding-3-large` |

## Examples

### Chat Completion Example

<<<<<<< HEAD
For an example of how to use the `/v1/chat/completions`, /v1/completions`, /v1/chat` endpoint, see the followings:

- [ `chat_completions_example.py` ](examples/chat_completions_example.py)
- [ `chat_completions_example_stream.py` ](examples/chat_completions_example_stream.py)
- [ `completions_example.py` ](examples/completions_example.py)
- [ `completions_example_stream.py` ](examples/completions_example_stream.py)
- [ `chat_example.py` ](examples/chat_example.py)
- # [ `chat_example_stream.py` ](examples/chat_example_stream.py)
- [chat_completions_example.py](examples/chat_completions_example.py)
- [chat_completions_example_stream.py](examples/chat_completions_example_stream.py)
- [completions_example.py](examples/completions_example.py)
- [completions_example_stream.py](examples/completions_example_stream.py)
- [chat_example.py](examples/chat_example.py)
- [chat_example_stream.py](examples/chat_example_stream.py)
  > > > > > > > 75e250f (docs: update README with improved formatting and details)

### Embedding Example

- [embedding_example.py](examples/embedding_example.py)

### o1 Chat Example

- [o1_chat_example.py](examples/o1_chat_example.py)

### OpenAI Client Example

- [openai_o3_chat_example.py](examples/o3_chat_example_pyclient.py)

## Bug Reports and Contributions

This project was developed in my spare time. Bugs and issues may exist. If you encounter any or have suggestions for improvements, please [open an issue](https://github.com/Oaklight/argo-proxy/issues/new) or [submit a pull request](https://github.com/Oaklight/argo-proxy/compare). Your contributions are highly appreciated!
