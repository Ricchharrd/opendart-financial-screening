# OpenDART Streamlit v2

This folder contains an updated Streamlit version of the OpenDART screening tool.

## What changed

- lets the user preview company candidates before running
- allows manual company selection when multiple DART matches exist
- keeps the multi-year screening flow
- shows multi-company trend charts with line graphs
- keeps Excel workbook export

## Run locally

```powershell
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Required secret

Recommended:

```toml
DART_API_KEY = "your_real_api_key"
```
