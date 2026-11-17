# Convenience entrypoints; workflow and configuration remain in openwrite.py.
.DEFAULT_GOAL := help
PYTHON ?= python3
VENV_PYTHON := .venv/bin/python

.PHONY: help setup doctor

help:
	@printf '%s\n' \
	  'make setup   初始化运行环境、安装依赖并生成 .env（已有配置不覆盖）' \
	  'make doctor  检查本地依赖与技能，不验证外部服务连接'

setup:
	@set -eu; \
	if [ ! -x "$(VENV_PYTHON)" ]; then \
	  if ! command -v "$(PYTHON)" >/dev/null 2>&1; then \
	    printf '%s\n' '未找到 Python，请先安装 Python 3，再运行 make setup。'; \
	    exit 1; \
	  fi; \
	  if command -v uv >/dev/null 2>&1; then \
	    uv venv .venv --python "$(PYTHON)"; \
	  elif ! "$(PYTHON)" -m venv .venv; then \
	    printf '%s\n' '无法创建虚拟环境，请安装 Python venv 支持（Ubuntu/Debian: sudo apt install python3-venv），或安装 uv 后重试。'; \
	    exit 1; \
	  fi; \
	fi; \
	if command -v uv >/dev/null 2>&1; then \
	  uv pip install --python "$(VENV_PYTHON)" -r requirements.txt; \
	else \
	  if ! "$(VENV_PYTHON)" -m pip --version >/dev/null 2>&1; then \
	    if ! "$(VENV_PYTHON)" -m ensurepip --upgrade; then \
	      printf '%s\n' '虚拟环境缺少 pip，请安装匹配 Python 版本的 venv 支持，或安装 uv 后重试。'; \
	      exit 1; \
	    fi; \
	  fi; \
	  "$(VENV_PYTHON)" -m pip install -r requirements.txt; \
	fi; \
	"$(VENV_PYTHON)" openwrite.py setup; \
	printf '%s\n' '初始化完成。请编辑项目根目录 .env；外部服务凭证按需填写。' \
	  '无需手动激活环境。检查环境：make doctor' \
	  '仅使用小红书时还需安装浏览器：.venv/bin/python -m playwright install chromium'

doctor:
	@if [ ! -x "$(VENV_PYTHON)" ]; then \
	  printf '%s\n' '请先运行 make setup。'; exit 1; \
	fi
	@"$(VENV_PYTHON)" openwrite.py doctor
