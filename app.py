"""
Compliance Engine - Streamlit Web Interface
A professional UI for checking document compliance against custom rules.
"""
import warnings
warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality")

import streamlit as st
import tempfile
import os
import time
from pathlib import Path

# Page configuration - must be first Streamlit command
st.set_page_config(
    page_title="Compliance Engine",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for styling
st.markdown("""
<style>
    /* Main container styling */
    .main {
        padding: 2rem;
    }
    
    /* Header styling */
    .header-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }
    
    .header-title {
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    
    .header-subtitle {
        font-size: 1.1rem;
        opacity: 0.9;
    }
    
    /* Score display */
    .score-container {
        text-align: center;
        padding: 2rem;
        border-radius: 15px;
        margin: 1rem 0;
    }
    
    .score-high {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        color: white;
    }
    
    .score-medium {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        color: white;
    }
    
    .score-low {
        background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%);
        color: white;
    }
    
    .score-value {
        font-size: 4rem;
        font-weight: 700;
    }
    
    .score-label {
        font-size: 1.2rem;
        opacity: 0.9;
    }
    
    /* Violation card */
    .violation-card {
        background: #fff;
        border-left: 4px solid #f45c43;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 10px 10px 0;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    
    .violation-header {
        font-weight: 600;
        color: #333;
        margin-bottom: 0.5rem;
    }
    
    .severity-badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
    }
    
    .severity-high {
        background: #fee2e2;
        color: #dc2626;
    }
    
    .severity-medium {
        background: #fef3c7;
        color: #d97706;
    }
    
    .severity-low {
        background: #dbeafe;
        color: #2563eb;
    }
    
    /* Upload area */
    .upload-section {
        background: #f8fafc;
        padding: 1.5rem;
        border-radius: 15px;
        border: 2px dashed #cbd5e1;
        margin: 1rem 0;
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.75rem 2rem;
        font-size: 1.1rem;
        font-weight: 600;
        border-radius: 10px;
        width: 100%;
        transition: transform 0.2s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
    }
    
    /* Info boxes */
    .info-box {
        color:black;
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    
    /* Success message */
    .success-box {
        background: #ecfdf5;
        border: 1px solid #a7f3d0;
        padding: 1.5rem;
        border-radius: 10px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)


def render_header():
    """Render the page header"""
    st.markdown("""
    <div class="header-container">
        <div class="header-title">⚖️ Compliance Engine</div>
        <div class="header-subtitle">
            Upload your compliance rules and check any document for violations instantly
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_score(score: float, is_compliant: bool, total_violations: int):
    """Render the compliance score"""
    if score >= 80:
        score_class = "score-high"
        emoji = "✅"
    elif score >= 50:
        score_class = "score-medium"
        emoji = "⚠️"
    else:
        score_class = "score-low"
        emoji = "❌"
    
    st.markdown(f"""
    <div class="score-container {score_class}">
        <div class="score-value">{emoji} {score:.0f}%</div>
        <div class="score-label">
            {"Compliant" if is_compliant else f"{total_violations} Violation(s) Found"}
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_violation(violation: dict, index: int):
    """Render a single violation card"""
    severity = violation.get('severity', 'medium').lower()
    severity_class = f"severity-{severity}" if severity in ['high', 'medium', 'low'] else "severity-medium"
    
    st.markdown(f"""
    <div class="violation-card">
        <div class="violation-header">
            {index}. {violation.get('rule_category', 'Unknown Category')}
            <span class="severity-badge {severity_class}">{severity}</span>
        </div>
        <p><strong>Issue:</strong> {violation.get('violation_text', 'No details')}</p>
        <p><strong>Suggestion:</strong> {violation.get('correction_suggestion', 'No suggestion')}</p>
    </div>
    """, unsafe_allow_html=True)


def main():
    """Main application"""
    render_header()
    
    # Description section
    st.markdown("""
    <div class="info-box">
        <strong>📋 How it works:</strong><br>
        1. Upload your compliance rules PDF (policy document, guidelines, etc.)<br>
        2. Paste or type the content you want to check<br>
        3. Click "Check Compliance" to get an instant analysis
    </div>
    """, unsafe_allow_html=True)
    
    # Two-column layout
    col1, col2 = st.columns([1, 1], gap="large")
    
    with col1:
        st.subheader("📄 Upload Rules Document")
        uploaded_file = st.file_uploader(
            "Upload your compliance rules PDF",
            type=['pdf'],
            help="Upload the PDF containing the rules/policies to check against"
        )
        
        if uploaded_file:
            st.success(f"✅ Uploaded: {uploaded_file.name}")
    
    with col2:
        st.subheader("✍️ Content to Check")
        user_content = st.text_area(
            "Paste or type the content to check for compliance",
            height=250,
            placeholder="Enter the document text, legal draft, or content you want to verify against the uploaded rules..."
        )
    
    # Check button
    st.markdown("<br>", unsafe_allow_html=True)
    
    check_button = st.button("🔍 Check Compliance", use_container_width=True)
    
    # Process compliance check
    if check_button:
        if not uploaded_file:
            st.error("⚠️ Please upload a rules PDF first")
        elif not user_content or len(user_content.strip()) < 10:
            st.error("⚠️ Please enter some content to check (at least 10 characters)")
        else:
            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(uploaded_file.read())
                tmp_path = tmp_file.name
            
            try:
                with st.spinner("🔄 Analyzing document for compliance..."):
                    # Import and run compliance check
                    from compliance import check_compliance
                    
                    result = check_compliance(
                        user_id=f"streamlit_user_{int(time.time())}",
                        file_path=tmp_path,
                        draft_text=user_content,
                        cleanup_after=True
                    )
                
                # Display results
                st.markdown("---")
                st.subheader("📊 Compliance Report")
                
                if result.get("status") == "success":
                    report = result.get("report", {})
                    
                    # Score display
                    render_score(
                        score=report.get("overallScore", 0),
                        is_compliant=report.get("is_compliant", False),
                        total_violations=report.get("totalViolations", 0)
                    )
                    
                    # Confidence
                    confidence = report.get("detectionConfidence", "Unknown")
                    st.info(f"🎯 Detection Confidence: **{confidence}**")
                    
                    # Violations
                    violations = report.get("violations", [])
                    if violations:
                        st.subheader("⚠️ Violations Found")
                        for i, v in enumerate(violations, 1):
                            render_violation(v, i)
                    else:
                        st.markdown("""
                        <div class="success-box">
                            <h3>🎉 Perfect Compliance!</h3>
                            <p>No violations were found in your document.</p>
                        </div>
                        """, unsafe_allow_html=True)
                
                elif result.get("status") == "failed":
                    errors = result.get("errors", ["Unknown error"])
                    st.error(f"❌ Compliance check failed: {', '.join(errors)}")
                else:
                    st.error(f"❌ Error: {result.get('message', 'Unknown error occurred')}")
                    
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
            finally:
                # Cleanup temp file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<p style='text-align: center; color: #64748b; font-size: 0.9rem;'>"
        "Built with ❤️ using Streamlit & Google Gemini AI"
        "</p>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
