import streamlit as st
import pandas as pd
import boto3
import uuid
import json
import requests
import time
import awswrangler as wr
import plotly.express as px
from wordcloud import WordCloud
import matplotlib.pyplot as plt

# --- 2. Page Configuration ---
st.set_page_config(
    page_title="ReviewLens AI",
    page_icon="렌즈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 3. App State Management ---
if 'page' not in st.session_state:
    st.session_state.page = 'Upload'
if 'job_id' not in st.session_state:
    st.session_state.job_id = ''
if 'upload_id' not in st.session_state:
    st.session_state.upload_id = None
if 'sample_job_id' not in st.session_state:
    st.session_state.sample_job_id = "031397e2653351a852d39b4075de3e13" # Example ETag

# --- 4. AWS Configuration & Connections ---
try:
    S3_BRONZE_BUCKET = st.secrets["S3_BRONZE_BUCKET"]
    GOLD_BUCKET_NAME = st.secrets["GOLD_BUCKET_NAME"]
    API_URL = st.secrets["API_URL"]
    AWS_REGION = st.secrets["AWS_DEFAULT_REGION"]
    AWS_ACCESS_KEY_ID = st.secrets["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_ACCESS_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
except KeyError as e:
    st.error(f"⚠️ Configuration Error: The secret '{e.args[0]}' is not set in Streamlit Cloud.")
    st.stop()

@st.cache_resource
def get_s3_client():
    return boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY, region_name=AWS_REGION)

# --- 5. Backend Communication Functions ---
def find_job_by_upload_id(upload_id):
    try:
        response = requests.get(f"{API_URL}/find-job/{upload_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return "ERROR"

def check_job_status(job_id):
    try:
        response = requests.get(f"{API_URL}/status/{job_id}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error checking job status: {e}")
        return None

def trigger_stitcher(job_id):
    try:
        response = requests.post(f"{API_URL}/stitch", json={"job_id": job_id})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error triggering finalization: {e}")
        return None

# --- 6. Data Loading Function ---
@st.cache_data(ttl=300)
def load_gold_data(job_id):
    try:
        return wr.s3.read_parquet(path=f"s3://{GOLD_BUCKET_NAME}/{job_id}.parquet")
    except Exception:
        st.warning("Could not load the final report. It may not be ready yet, or the Job ID is incorrect.")
        return pd.DataFrame()

# --- 7. UI Page Rendering Functions ---

def render_upload_page():
    st.title("Welcome to ReviewLens AI! 🚀")
    st.markdown("Turn your customer reviews into **actionable insights**. Upload a CSV, map your columns, and let our AI pipeline do the rest.")

    if st.button("✨ Try with a Sample Dataset (Demo Mode)"):
        if st.session_state.sample_job_id == "YOUR_SAMPLE_JOB_ID_HERE":
            st.error("To enable demo mode, please set a valid `sample_job_id` in the frontend code.")
        else:
            st.session_state.job_id = st.session_state.sample_job_id
            st.session_state.page = 'Results'
            st.rerun()

    st.header("1. Upload Your Review Data")
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

    if uploaded_file:
        df_preview = pd.read_csv(uploaded_file, nrows=5)
        st.dataframe(df_preview, use_container_width=True)
        st.header("2. Map Your Columns")
        
        with st.form("mapping_form"):
            review_text_col = st.selectbox("Which column contains the **review text**? (Required)", [None] + list(df_preview.columns))
            title_col = st.selectbox("Which column contains the review **title**? (Optional)", [None] + list(df_preview.columns))
            
            submitted = st.form_submit_button("Start Analysis")
            if submitted:
                if not review_text_col:
                    st.error("Mapping the review text column is required.")
                else:
                    # Pass both values (one might be None) to the backend handler
                    column_map = {
                        "review_text_col": review_text_col,
                        "title_col": title_col
                    }
                    start_backend_pipeline(uploaded_file, column_map)

def start_backend_pipeline(uploaded_file, column_map):
    upload_id = str(uuid.uuid4())
    file_key = f"uploads/{upload_id}/{uploaded_file.name}"
    
    # Build the mapping payload for the backend ---
    # This include the 'title' if it was selected by the user.
    final_mapping = {
        "full_review_text": column_map.get("review_text_col"),
        "title": column_map.get("title_col")
    }
    # Clean out any 'None' values (e.g., if title was not mapped)
    final_mapping = {k: v for k, v in final_mapping.items() if v is not None}

    with st.spinner(f"Uploading file..."):
        try:
            uploaded_file.seek(0)
            get_s3_client().put_object(
                Bucket=S3_BRONZE_BUCKET,
                Key=file_key,
                Body=uploaded_file,
                # Send the correct key 'mapping' with the full JSON payload
                Metadata={"mapping": json.dumps(final_mapping)}
            )
            st.session_state.upload_id = upload_id
            st.session_state.job_id = ''
            st.session_state.page = 'Monitor Job'
            st.rerun()
        except Exception as e:
            st.error(f"Upload failed: {e}")

def render_monitoring_page():
    st.title("Analysis in Progress... ⚙️")
    
    if not st.session_state.get('job_id'):
        if st.session_state.get('upload_id'):
            with st.spinner("Finding your job in the system..."):
                time.sleep(5)
                job_info = find_job_by_upload_id(st.session_state.upload_id)
                if job_info and job_info != "ERROR":
                    st.session_state.job_id = job_info.get('job_id')
                    st.rerun()
                elif job_info == "ERROR":
                    st.error("Could not find the job. Please check the API URL.")
                    return
                else:
                    st.warning("Your job is being registered. This page will refresh shortly...")
                    time.sleep(10)
                    st.rerun()
        else:
            st.warning("No active job found. Please upload a file first.")
            return

    job_id = st.session_state.job_id
    st.header(f"Monitoring Job ID: `{job_id}`")
    status_placeholder = st.empty()
    with st.spinner("Fetching latest status..."):
        status = check_job_status(job_id)

    if status:
        with status_placeholder.container():
            current_status = status.get('status', 'LOADING...')
            progress = status.get('progress_percentage', 0)
            st.info(f"**Status:** {current_status}")
            st.progress(int(progress), text=f"{progress:.2f}% Complete")
            with st.expander("Show Raw Status Details"):
                st.json(status)
            
            if current_status == 'PROCESSING_COMPLETE':
                if st.button("🔗 Generate Final Report"):
                    with st.spinner("Finalizing results..."):
                        trigger_stitcher(job_id)
                    st.success("Finalization started! Refreshing...")
                    time.sleep(5)
                    st.rerun()
            elif current_status == 'COMPLETED':
                st.balloons()
                st.success("Analysis Complete!")
                if st.button("📊 View Results"):
                    st.session_state.page = 'Results'
                    st.rerun()
            elif 'FAILED' in current_status:
                st.error(f"The job has failed with status: {current_status}.")
            else:
                time.sleep(10)
                st.rerun()
    else:
        st.error("Could not retrieve status for this Job ID.")

def render_results_page():
    st.title("Analysis Results 📊")
    job_id = st.session_state.get('job_id')
    if not job_id:
        st.warning("Please upload a file or use the demo to see results.")
        return

    st.header(f"Showing results for Job ID: `{job_id}`")
    df = load_gold_data(job_id)

    if not df.empty:
        st.subheader("Key Metrics")
        cols = st.columns(3)
        cols[0].metric("Total Reviews Analyzed", f"{len(df):,}")
        
        if 'sentiment' in df.columns:
            positive_percentage = (df['sentiment'] == 'POSITIVE').mean() * 100
            cols[1].metric("Positive Sentiment", f"{positive_percentage:.1f}%")

        if 'rating' in df.columns:
            avg_rating = df['rating'].mean()
            cols[2].metric("Average Rating", f"{avg_rating:.2f} ★")

        tab1, tab2, tab3 = st.tabs(["Sentiment & Topics", "Aspect Analysis", "Data Explorer"])

        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Sentiment Distribution")
                if 'sentiment' in df.columns:
                    fig = px.pie(df, names='sentiment', hole=0.3, color='sentiment', color_discrete_map={'POSITIVE':'#2ca02c', 'NEGATIVE':'#d62728', 'ERROR':'grey'})
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("What are people talking about?")
                if 'zero_shot_topic' in df.columns:
                    topic_counts = df['zero_shot_topic'].value_counts().reset_index()
                    fig2 = px.bar(topic_counts, y='zero_shot_topic', x='count', title='Top Discussion Topics', orientation='h')
                    st.plotly_chart(fig2, use_container_width=True)

        with tab2:
            st.subheader("Aspect-Based Word Cloud")
            if 'aspects' in df.columns and df['aspects'].nunique() > 1:
                st.info("The most frequently mentioned aspects.")
                text = ' '.join(df['aspects'].dropna().astype(str).str.replace(r' \([^)]*\)', '', regex=True))
                if text:
                    wordcloud = WordCloud(width=800, height=400, background_color='white', colormap='viridis').generate(text)
                    fig, ax = plt.subplots()
                    ax.imshow(wordcloud, interpolation='bilinear')
                    ax.axis('off')
                    st.pyplot(fig)
                else:
                    st.info("No aspects found to generate a word cloud.")
            else:
                st.info("No aspect data available.")

        with tab3:
            st.subheader("Explore All Data")
            st.dataframe(df, use_container_width=True)


# --- 8. Main App Router ---
st.sidebar.title("ReviewLens AI")
page_options = ['Upload', 'Monitor Job', 'Results']

page_selection = st.sidebar.radio(
    "Navigation",
    page_options,
    index=page_options.index(st.session_state.page)
)

if page_selection != st.session_state.page:
    st.session_state.page = page_selection
    st.rerun()

if st.session_state.page == 'Upload':
    render_upload_page()
elif st.session_state.page == 'Monitor Job':
    render_monitoring_page()
elif st.session_state.page == 'Results':
    render_results_page()