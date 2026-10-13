"""Keep public demonstration edits in one browser session's temporary directory."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import streamlit as st
from .config import ROOT

def workspace_root():
    if os.getenv('FOUNDEROS_WORKSPACE_MODE', 'session') == 'local':
        return ROOT
    if '_founderos_workspace' not in st.session_state:
        st.session_state['_founderos_workspace'] = TemporaryDirectory(prefix='founderos-demo-')
    return Path(st.session_state['_founderos_workspace'].name)
