
# Forktex Python CLI 🚀

[![PyPI version](https://img.shields.io/pypi/v/forktex.svg)](https://pypi.org/project/forktex/)
[![Python Versions](https://img.shields.io/pypi/pyversions/forktex.svg)](https://pypi.org/project/forktex/)

[![Publish](https://github.com/forktex/forktex-python/actions/workflows/publish.yml/badge.svg)](https://github.com/forktex/forktex-python/actions)

**Forktex** is the official Python CLI & SDK for interacting with the [Forktex API](https://forktex.com).  
It enables developers and teams to call AI models, manage cloud resources, and integrate Forktex services directly from the terminal or Python scripts.

---

## ✨ Features

- 🤖 **AI models** — call Forktex-hosted AI models with simple CLI commands  
- ☁️ **Cloud resource management** — create, manage, and monitor Forktex cloud resources  
- 🛠️ **Developer-friendly** — designed for automation, CI/CD, and scripting  
- 📦 **PyPI-ready** — install & upgrade via pip

---

## 📦 Installation

```bash
pip install forktex
```

Upgrade to the latest version anytime:

```bash
pip install --upgrade forktex
```

---

## 🚀 Quickstart (CLI)

After installation, the `forktex` CLI is available globally:

```bash
forktex --help
```

### Example: Call an AI model

```bash
forktex ai call --model ro-hero --prompt "Hello, world!"
```

### Example: Manage cloud resources

```bash
forktex cloud list
forktex cloud create --type vm --name test-vm
```

---

## ⚙️ Configuration

You’ll need an API key from the [Forktex Dashboard](https://forktex.com).

Set it as an environment variable:

```bash
export FORKTEX_API_KEY="your_api_key_here"
```

Or configure via CLI:

```bash
forktex config set api_key your_api_key_here
```

---

## 📖 Usage as a Python Library

You can also use Forktex as a Python SDK:

```python
from forktex import Client

client = Client(api_key="your_api_key")

# Call an AI model
result = client.ai.call(model="ro-hero", prompt="Hello world!")
print(result.output)

# List cloud resources
resources = client.cloud.list()
print(resources)
```

---


## 🤝 Contributing

Contributions are welcome!  
- Open issues and feature requests at [GitHub Issues](https://github.com/forktex/forktex-python/issues)  
- Submit PRs to improve the library and CLI  

---
