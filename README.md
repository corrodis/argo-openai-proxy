# argo-openai-proxy

## Getting started

To make it easy for you to get started with GitLab, here's a list of recommended next steps.

- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
  - [Natively](#natively)
  - [Using Docker](#using-docker)
- [Folder Structure](#folder-structure)
- [Endpoints](#endpoints)
- [Examples](#examples)

## Add your files

- [ ] [Create](https://docs.gitlab.com/ee/user/project/repository/web_editor.html#create-a-file) or [upload](https://docs.gitlab.com/ee/user/project/repository/web_editor.html#upload-a-file) files
- [ ] [Add files using the command line](https://docs.gitlab.com/topics/git/add_files/#add-files-to-a-git-repository) or push an existing Git repository with the following command:

## Configuration

The application is configured using a `config.yaml` file. This file contains settings such as the ARGO API URLs, port number, and logging behavior. Below is a breakdown of the configuration options:

### Configuration Options

- **`port`**: The port number on which the application will listen. Default is `44497`.
- **`argo_url`**: The URL of the ARGO API for chat and completions. Default is `"https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/"`.
- **`argo_embedding_url`**: The URL of the ARGO API for embeddings. Default is `"https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/embed/"`.
- **`user`**: The user name to be used in the requests. Default is `"cels"`.
- **`verbose`**: A boolean flag to control whether to print input and output for debugging. Default is `true`.
- **`num_workers`**: The number of worker processes for Gunicorn. Default is `5`.
- **`timeout`**: The timeout for requests in seconds. Default is `600`.

### Example `config.yaml`

```yaml
port: 44497
argo_url: "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/"
argo_embedding_url: "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/embed/"
user: "cels"
verbose: true
num_workers: 5
timeout: 600
```

## Integrate with your tools

- [ ] [Set up project integrations](https://gitlab.osti.gov/ai-at-argonne/argo-gateway-api/argo-proxy-tools/argo-openai-proxy/-/settings/integrations)

## Collaborate with your team

- [ ] [Invite team members and collaborators](https://docs.gitlab.com/ee/user/project/members/)
- [ ] [Create a new merge request](https://docs.gitlab.com/ee/user/project/merge_requests/creating_merge_requests.html)
- [ ] [Automatically close issues from merge requests](https://docs.gitlab.com/ee/user/project/issues/managing_issues.html#closing-issues-automatically)
- [ ] [Enable merge request approvals](https://docs.gitlab.com/ee/user/project/merge_requests/approvals/)
- [ ] [Set auto-merge](https://docs.gitlab.com/user/project/merge_requests/auto_merge/)

## Test and Deploy

Use the built-in continuous integration in GitLab.

- [ ] [Get started with GitLab CI/CD](https://docs.gitlab.com/ee/ci/quick_start/)
- [ ] [Analyze your code for known vulnerabilities with Static Application Security Testing (SAST)](https://docs.gitlab.com/ee/user/application_security/sast/)
- [ ] [Deploy to Kubernetes, Amazon EC2, or Amazon ECS using Auto Deploy](https://docs.gitlab.com/ee/topics/autodevops/requirements.html)
- [ ] [Use pull-based deployments for improved Kubernetes management](https://docs.gitlab.com/ee/user/clusters/agent/)
- [ ] [Set up protected environments](https://docs.gitlab.com/ee/ci/environments/protected_environments.html)

---

# Editing this README

When you're ready to make this README your own, just edit this file and use the handy template below (or feel free to structure it however you want - this is just a starting point!). Thanks to [makeareadme.com](https://www.makeareadme.com/) for this template.

## Suggestions for a good README

Every project is different, so consider which of these sections apply to yours. The sections used in the template are suggestions for most open source projects. Also keep in mind that while a README can be too long and detailed, too long is better than too short. If you think your README is too long, consider utilizing another form of documentation rather than cutting out information.

## Name

Choose a self-explaining name for your project.

## Description

## Folder Structure

```
$ tree .
.
├── app.py
├── argoproxy
│   ├── chat.py
│   ├── completions.py
│   ├── embed.py
│   ├── extras.py
│   └── utils.py
├── compose.yaml
├── config.yaml
├── Dockerfile
├── Dockerfile.txt
├── README.md
├── requirements.txt
├── run_app.sh
└── test
    ├── chat_example.py
    ├── embedding_example.py
    └── o1-example.py

2 directories, 16 files
```

## Endpoints

The application provides the following endpoints:

- **`/v1/chat`**: Directly proxies requests to the ARGO API.
- **`/v1/chat/completions`**: Proxies requests to the ARGO API and converts the response to OpenAI-compatible format.
- **`/v1/completions`**: Proxies requests to the ARGO API and converts the response to OpenAI-compatible format (legacy).
- **`/v1/embed`**: Proxies requests to the ARGO Embedding API.
- **`/v1/models`**: Returns a list of available models in OpenAI-compatible format.
- **`/v1/status`**: Returns a simple "hello" response from GPT-4o.

## Examples

### Chat Example

For an example of how to use the `/v1/chat/completions` endpoint, see the [ `chat_example.py` ](test/chat_example.py) file.

### Embedding Example

For an example of how to use the `/v1/embed` endpoint, see the [ `embedding_example.py` ](test/embedding_example.py) file.

### O1 Example

For an example of how to use the `/v1/chat` endpoint with the `argo:gpt-o1-preview` model, see the [ `o1-example.py` ](test/o1-example.py) file.

---

### **Changes Made**

1. Added the **Configuration** section with a detailed explanation of the `config.yaml` file and its options.
2. Included an example `config.yaml` file for reference.
3. Ensured the **Configuration** section is properly linked in the Table of Contents.
