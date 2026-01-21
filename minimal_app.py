"""
Minimal Streamlit App for UI Stability Diagnostic
==================================================
No custom CSS. No imports. No auth. No DB.
Purpose: Isolate sidebar resizer jumpiness cause.
"""

import streamlit as st

st.set_page_config(layout="wide")

# Sidebar
with st.sidebar:
    st.header("Sidebar")
    st.radio("Mode", ["A", "B"])
    st.slider("Value", 0, 100)
    st.button("Click")

# Main area
st.header("Main")
st.write("""
**TEST PROCEDURE:**

1. Hover the sidebar edge until the resize cursor appears
2. Click once (do not drag)
3. Observe: does the layout jump? (yes/no)
4. Repeat in a different browser

**Streamlit version:**
""")
st.code(st.__version__)
