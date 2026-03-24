@echo off
cd /d D:\arxiv_obsidian_pipeline
call .venv\Scripts\activate
set HTTP_PROXY=http://127.0.0.1:7897
set HTTPS_PROXY=http://127.0.0.1:7897
python src\main.py