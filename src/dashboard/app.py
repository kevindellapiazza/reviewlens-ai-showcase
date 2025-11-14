"""
ReviewLens AI: Streamlit Frontend

This application serves as the user-facing interface for the
ReviewLens AI pipeline. It allows users to:
1.  Upload their own CSV data for analysis.
2.  View a pre-analyzed demo report instantly.
3.  Download a sample CSV to run a full, live pipeline test.
4.  Map CSV columns to the required backend fields.
5.  Configure dynamic AI models (Zero-Shot and ABSA labels).
6.  Monitor the asynchronous job processing in real-time.
7.  View and interact with the final, enriched dashboard.

This app is fully decoupled from the backend and communicates
via a secure, serverless API Gateway.
"""

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
from io import StringIO, BytesIO
import os
from collections import Counter

# --- 1. Page Configuration ---
st.set_page_config(
    page_title="ReviewLens AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. App State Management ---
# Use session_state to manage page navigation, job IDs, and error states.
if 'page' not in st.session_state:
    st.session_state.page = 'Upload'
if 'job_id' not in st.session_state:
    st.session_state.job_id = ''
if 'upload_id' not in st.session_state:
    st.session_state.upload_id = None
if 'api_error' not in st.session_state:
    st.session_state.api_error = False
if 'stitch_triggered' not in st.session_state:
    st.session_state.stitch_triggered = False

# Pre-analyzed Job ID is used for the "Instant Demo" path.
st.session_state.sample_job_id = "94f5a0f1e53d590db9c046210e9049a4" 


# --- 3. AWS Configuration & Connections ---
try:
    # Load all credentials and endpoints from Streamlit's secure secrets
    S3_BRONZE_BUCKET = st.secrets["S3_BRONZE_BUCKET"]
    GOLD_BUCKET_NAME = st.secrets["GOLD_BUCKET_NAME"]
    API_URL = st.secrets["API_URL"]
    AWS_REGION = st.secrets["AWS_DEFAULT_REGION"]
    AWS_ACCESS_KEY_ID = st.secrets["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_ACCESS_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
    
    # Configure the default session for awswrangler (used for reading Gold data)
    boto3.setup_default_session(
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )
    
except KeyError as e:
    # Stop the app if critical secrets are missing
    st.error(f"⚠️ Configuration Error: The secret '{e.args[0]}' is not set. Please check your .streamlit/secrets.toml file.")
    st.stop()

@st.cache_resource
def get_s3_client():
    """
    Gets a Boto3 S3 client.
    Using @st.cache_resource ensures this client is created only once.
    """
    return boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )

# --- 4. Backend Communication Functions ---

def find_job_by_upload_id(upload_id: str) -> dict | str | None:
    """
    Polls the /find-job API to get the real job_id from an upload_id.
    This is the "smart polling" that decouples the frontend from the ETag.
    """
    try:
        response = requests.get(f"{API_URL}/find-job/{upload_id}")
        if response.status_code == 404:
            return None  # Job not found yet, still processing
        response.raise_for_status() # Raise an exception for 5xx errors
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Error (find_job_by_upload_id): {e}")
        return "ERROR"

def check_job_status(job_id: str) -> dict | None:
    """Gets the latest status of a job from the /status API."""
    try:
        response = requests.get(f"{API_URL}/status/{job_id}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Error (check_job_status): {e}")
        st.session_state.api_error = True
        return None

def trigger_stitcher(job_id: str) -> dict | None:
    """
    Calls the /stitch API asynchronously ("fire and forget").
    
    We send the request but use a very short timeout. We EXPECT
    the request to time out (a ReadTimeout), as the Lambda takes
    minutes to run. We catch this expected timeout and treat it as a 
    success, allowing the Streamlit frontend to continue.
    """
    try:
        # Send the POST request, but set a 3-second client-side timeout.
        response = requests.post(
            f"{API_URL}/stitch", 
            json={"job_id": job_id}, 
            timeout=3
        )
        
        # --- PATH 1: UNEXPECTED FAST RESPONSE (Lambda Error) ---
        # If the server does respond in < 3 seconds, it's an error.
        response.raise_for_status()
        print(f"API Error (trigger_stitcher): Lambda responded too quickly. {response.json()}")
        st.error(f"Error triggering finalization: {response.json().get('error', 'Unknown error')}")
        return None

    except requests.exceptions.ReadTimeout:
        # --- PATH 2: EXPECTED TIMEOUT (Success) ---
        # API Gateway accepted the request, the Lambda is running.
        print("Stitcher call timed out (AS EXPECTED). Lambda is running in the background.")
        
        # Return a mock success status to the frontend
        return {"status": "STITCHING_STARTED"}

    except requests.exceptions.RequestException as e:
        # --- PATH 3: REAL NETWORK ERROR ---
        # This catches other errors (e.g., 404, 503, DNS failure) that are not a ReadTimeout.
        print(f"API Error (trigger_stitcher): {e}")
        st.error(f"Error triggering finalization: {e}")
        return None

# --- 5. Data Loading Functions ---

@st.cache_data(ttl=300)
def load_gold_data(job_id: str) -> pd.DataFrame:
    """
    Loads the final Parquet file from the Gold S3 bucket.
    Uses @st.cache_data to cache the result for 5 minutes.
    """
    try:
        s3_path = f"s3://{GOLD_BUCKET_NAME}/{job_id}.parquet"
        print(f"Attempting to load data from: {s3_path}")
        df = wr.s3.read_parquet(path=s3_path)
        print(f"Successfully loaded {len(df)} rows.")
        return df
    except Exception as e:
        print(f"Failed to load gold data for job {job_id}: {e}")
        st.warning(f"Could not load the final report for job {job_id}. It may not be ready, or the Job ID is incorrect.")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_topic_info(job_id: str) -> pd.DataFrame:
    """
    Loads the BERTopic info Parquet file from the Gold S3 bucket.
    Caches the result for 5 minutes.
    """
    try:
        s3_path = f"s3://{GOLD_BUCKET_NAME}/{job_id}_topics.parquet"
        print(f"Attempting to load topic info from: {s3_path}")
        df = wr.s3.read_parquet(path=s3_path)
        print(f"Successfully loaded {len(df)} topics.")
        return df
    except Exception as e:
        print(f"Could not load topic info file for job {job_id}: {e}")
        return pd.DataFrame()

# --- 6. UI Page Rendering Functions ---

def render_upload_page():
    """Renders the main file upload and column mapping page."""
    st.title("Welcome to ReviewLens AI! 🚀")
    st.markdown("Turn your customer reviews into **actionable insights**. Upload a CSV, map your columns, and let our AI pipeline do the rest.")

    with st.expander("How This Pipeline Works (For Recruiters)"):
        st.markdown("""
        This app demonstrates a complete, event-driven, serverless AI pipeline built on AWS.
        
        1.  **Upload & Trigger:** When you upload a CSV, it's saved to an **S3 Bronze Bucket**. This event triggers the first AWS Lambda (`splitter-lambda`).
        2.  **Orchestration:** The `splitter-lambda` reads your mapping, splits the file, and starts an **AWS Step Function** execution *for each batch*.
        3.  **Parallel AI Analysis:** The Step Function orchestrates three different AI models in sequence for each batch:
            * **Sentiment Lambda:** Adds overall sentiment.
            * **Zero-Shot Lambda:** Adds dynamic topics (using your labels below).
            * **ABSA Lambda:** Adds fine-grained aspects (using your labels below).
        4.  **Aggregation:** When you click "Generate Final Report", the `stitcher-lambda` runs, aggregates all batches, runs a final **BERTopic** model, and saves the final file to the **S3 Gold Bucket**.
        5.  **Dashboard:** The "Results" page queries this final file to build the dashboard.
        
        The full backend source code (`src/`) and infrastructure-as-code (`terraform/`) are available in this repository for review.
        """)
    
    st.subheader("Option 1: View Pre-Analyzed Report (Instant)")
    st.markdown("Click this button to skip processing and instantly view a completed dashboard from a pre-analyzed job.")
    
    # This is the "Test Job" button for an instant demo.
    # It works by setting the job_id directly and navigating to the Results page.
    if st.session_state.sample_job_id:
        if st.button("✨ View Pre-Analyzed Report"):
            st.session_state.job_id = st.session_state.sample_job_id
            st.session_state.page = 'Results' # Go straight to the results
            st.rerun()

    st.subheader("Option 2: Launch a Live Pipeline Test")
    st.markdown("Upload your own CSV or use our sample file to trigger the full, live AWS backend pipeline. (Est. time: 5-7 minutes)")

    # --- Download Sample CSV Button ---
    try:
        # Build the relative path to the sample file
        base_path = os.path.dirname(__file__)
        sample_file_path = os.path.join(base_path, "../../docs/sample_reviews.csv")
        
        with open(sample_file_path, "rb") as f:
            csv_data = f.read()
        
        st.download_button(
            label="📄 Download Sample CSV",
            data=csv_data,
            file_name="sample_reviews.csv",
            mime="text/csv",
            help="Download the sample CSV file to test the upload functionality yourself."
        )
    except FileNotFoundError:
        st.warning(f"Could not find sample file at: {sample_file_path}")
    except Exception as e:
        st.warning(f"Could not load sample file for download: {e}")

    # This is the "Live Test" path
    uploaded_file = st.file_uploader("Upload your CSV file", type="csv")

    if uploaded_file:
        try:
            # Read just the header and first 5 rows for preview
            df_preview = pd.read_csv(uploaded_file, nrows=5)
            uploaded_file.seek(0) # Rewind the file for the real upload
            
            st.dataframe(df_preview, use_container_width=True)
            st.header("Map Columns & Configure AI")
            
            # Use a form to batch user inputs
            with st.form("mapping_form"):
                st.subheader("Column Mapping")
                st.markdown("Tell the AI which columns to read from your CSV.")
                cols = st.columns(3)
                csv_columns = [None] + list(df_preview.columns)
                review_text_col = cols[0].selectbox("Review Text (Required)", csv_columns, help="The column containing the main review text.")
                title_col = cols[1].selectbox("Review Title (Optional)", csv_columns, help="The column containing the review title (if any).")
                rating_col = cols[2].selectbox("Rating (Optional)", csv_columns, help="The column containing the 1-5 star rating.")
                
                st.subheader("AI Configuration (Optional)")
                st.info("Customize the AI for your specific data. **If you leave these blank**, the system will use general-purpose defaults.")
                
                cols_ai = st.columns(2)
                zero_shot_labels = cols_ai[0].text_area("Categories (Zero-Shot)", 
                                                        placeholder="e.g., price, shipping, customer service, battery life, screen quality",
                                                        help="Provide a comma-separated list of the **main topics** you want to track.")
                absa_labels = cols_ai[1].text_area("Aspects (ABSA)", 
                                                   placeholder="e.g., slow delivery, good quality, poor fit, high price, battery drains fast, bright screen",
                                                   help="Provide a comma-separated list of **specific features/opinions** you want to extract.")
                
                submitted = st.form_submit_button("Start Analysis")
                if submitted:
                    if not review_text_col:
                        st.error("Mapping the review text column is required.")
                    else:
                        # Package all user inputs into the mapping dict
                        column_map = {
                            "full_review_text": review_text_col,
                            "title": title_col,
                            "rating": rating_col,
                            "zero_shot_labels": zero_shot_labels,
                            "absa_labels": absa_labels
                        }
                        # Call the backend pipeline
                        start_backend_pipeline(uploaded_file, column_map)
        except Exception as e:
            st.error(f"An error occurred while reading the CSV: {e}")
            st.info("Please ensure your file is a valid CSV and not empty.")


def start_backend_pipeline(uploaded_file, column_map: dict):
    """
    Handles the S3 upload and metadata attachment to trigger the backend.
    """
    # Create a unique 'upload_id' (UUID) for this specific frontend session
    upload_id = str(uuid.uuid4())
    file_key = f"uploads/{upload_id}/{uploaded_file.name}"
    
    # Filter out any empty mappings (e.g., if 'title' was not provided)
    final_mapping = {k: v for k, v in column_map.items() if v}

    with st.spinner(f"Uploading file to S3 Bronze bucket..."):
        try:
            uploaded_file.seek(0)
            file_body = uploaded_file.read() # Read the file's content
            
            # Use the cached S3 client to upload
            get_s3_client().put_object(
                Bucket=S3_BRONZE_BUCKET,
                Key=file_key,
                Body=file_body, # Pass the file bytes
                Metadata={"mapping": json.dumps(final_mapping)} # Pass config as metadata
            )
            
            # Set the state for the monitoring page
            st.session_state.upload_id = upload_id
            st.session_state.job_id = '' 
            st.session_state.page = 'Monitor Job'
            st.rerun()
            
        except Exception as e:
            st.error(f"Upload failed: {e}")
            st.error("Please check your AWS credentials (st.secrets) and S3 bucket permissions.")

def render_monitoring_page():
    """Renders the job monitoring page, polling for status updates."""
    st.title("Analysis in Progress... ⚙️")
    
    # --- Performance Note for Recruiters ---
    with st.info("A Note on Performance (For Recruiters & Technical Reviewers)"):
        st.markdown("""
        You are running a **live, end-to-end analysis** on the AWS backend. Please allow **3-5 minutes** for the 500-row sample to process through all 4 AI models.

        This demo is intentionally optimized for **minimum cost (scale-to-zero)**, not raw speed, to keep this public portfolio affordable.
        
        **Production-Grade Optimizations (The MLOps Trade-Offs):**
        
        The current latency is a direct result of these cost-saving decisions. To meet production-level requirements, the following optimizations would be applied:

        * **Memory/vCPU:** Lambdas are set to `3008MB` (the maximum for this account type). This provides ~2 vCPUs. Increasing this limit or using compute-optimized Lambdas would drastically cut inference time.
        * **Cold Starts:** You are experiencing the full "cold start" for 5 Docker container images. For a low-latency API, **Provisioned Concurrency** (warm-ups) would be enabled to eliminate this.
        * **Concurrency:** The pipeline is limited by the default AWS account concurrency (10 parallel Lambdas). This creates a bottleneck; for a production load, this limit would be raised.
        * **Alternative Compute Layer:** For a high-throughput, real-time API, these models would be deployed to dedicated **AWS SageMaker Endpoints**. For massive, multi-million row batch jobs, the compute tasks would be shifted from Lambda to **AWS Batch** or **Fargate**, while retaining the same serverless orchestration (Step Functions) and triggers (S3/API Gateway).
        """)
    
    st.session_state.api_error = False

    # --- Step 1: Find the real job_id ---
    if not st.session_state.get('job_id'):
        if st.session_state.get('upload_id'):
            with st.spinner("Finding your job in the system... (This may take a moment for the S3 trigger to fire)"):
                job_info = None
                for _ in range(5): # Poll 5 times (25 seconds total)
                    job_info = find_job_by_upload_id(st.session_state.upload_id)
                    
                    if job_info == "ERROR":
                        st.error("Could not contact the API. Please check the API URL and permissions.")
                        st.session_state.api_error = True
                        return
                    if job_info:
                        st.session_state.job_id = job_info.get('job_id')
                        st.rerun() # Rerun the page to move to Step 2
                    
                    time.sleep(5) # Wait 5 seconds between polls
                
                st.warning("Your job is being registered. This page will refresh shortly...")
                time.sleep(10) 
                st.rerun()
        else:
            st.warning("No active job found. Please upload a file first.")
            return

    # --- Step 2: Poll for status (This block runs ONLY if we have a job_id) ---
    job_id = st.session_state.job_id
    st.header(f"Monitoring Job ID: `{job_id}`")
    status_placeholder = st.empty()
    
    with st.spinner("Fetching latest status..."):
        status = check_job_status(job_id)

    if st.session_state.api_error:
        st.error("Could not contact the API. Please check the API URL and permissions.")
        return

    # This is the main frontend state machine
    if status:
        # Extract variables once
        current_status = status.get('status', 'LOADING...')
        progress = status.get('progress_percentage', 0)
        
        # --- Race Condition fix---
        # If we have *already triggered* the stitcher, but DynamoDB hasn't updated yet, *force* the status to 'STITCHING'
        # to prevent the UI from flickering back to the previous state.
        if st.session_state.stitch_triggered and current_status == 'PROCESSING_COMPLETE':
            current_status = 'STITCHING'
        
        # --- State: Batches are processed, ready to stitch ---
        if current_status == 'PROCESSING_COMPLETE':
            with status_placeholder.container():
                st.info(f"**Status:** {current_status}")
                st.progress(int(progress), text=f"Processing Batches (Step 1/2)... {progress:.0f}%")
                st.success("All batches processed! Ready to generate the final report.")
                
                if st.button("🔗 Generate Final Report (Run Stitcher)"):
                    with st.spinner("Sending finalization request..."):
                        trigger_response = trigger_stitcher(job_id)
                    
                    if trigger_response:
                        # Set a *persistent* flag that we have clicked this.
                        # This flag will only be reset when the job is COMPLETED or FAILED.
                        st.session_state.stitch_triggered = True
                        st.rerun() # Rerun immediately
                    else:
                        # Error was already shown by trigger_stitcher function
                        pass
        
        # --- State: Stitching is done, report is ready ---
        elif current_status == 'COMPLETED':
            st.session_state.stitch_triggered = False # Reset the flag
            with status_placeholder.container():
                st.info(f"**Status:** {current_status}")
                st.progress(100, text="100.00% Complete")
                st.balloons()
                st.success("Analysis Complete! Final report is now available.")
                
                # S3 Eventual Consistency Fix
                with st.spinner("Finalizing report..."):
                    time.sleep(5)
                
                if st.button("📊 View Results"):
                    st.session_state.page = 'Results'
                    st.rerun()
        
        # --- State: A fatal error occurred ---
        elif 'FAILED' in current_status:
            st.session_state.stitch_triggered = False # Reset the flag
            with status_placeholder.container():
                st.error(f"The job has failed with status: {current_status}.")
                st.error(f"Error details: {status.get('error_message', 'No details provided.')}")
        
        # --- State: Still processing (IN_PROGRESS or STITCHING), auto-refresh ---
        elif current_status in ['IN_PROGRESS', 'STITCHING']:
            with status_placeholder.container():
                st.info(f"**Status:** {current_status}")
                
                if current_status == 'STITCHING':
                    # This is the "second progress bar"
                    st.progress(50, text="Finalizing Report (Step 2/2)...50%")
                else:
                    # This is the "first progress bar"
                    st.progress(int(progress), text=f"Processing Batches (Step 1/2)... {progress:.0f}%")

                # This is the auto-refresh loop
                time.sleep(10) # Wait 10 seconds and poll again
                st.rerun()
                
    else:
        st.error("Could not retrieve status for this Job ID. The API might be down or the ID is incorrect.")

def render_results_page():
    """Renders the final dashboard with metrics and charts."""
    st.title("Analysis Results 📊")
    job_id = st.session_state.get('job_id')
    if not job_id:
        st.warning("Please upload a file or use the demo to see results.")
        return

    st.header(f"Showing results for Job ID: `{job_id}`")
    
    # --- Analyst's Guide Expander ---
    with st.expander("How to Read This Dashboard (An Analyst's Guide)"):
        st.markdown("""
        This dashboard provides a 4-layer "insight funnel" to move from a high-level overview to specific, actionable problems. Use the filters at the top to drill down.

---

### 1. Tab: Sentiment & Topics (The "What" and "Why")

This tab answers your first two questions: "What is the overall sentiment?" and "Why?"

* **Sentiment (Pie Chart):** This is your high-level KPI. It shows the overall brand health at a glance.
* **Topics (Bar Chart):** This shows *what* customers are talking about, using the categories you provided during upload (e.g., `price`, `shipping`).

* **💡 PRO-TIP (Action):**
    1.  Use the **"Filter by Sentiment"** dropdown and select **"NEGATIVE"**.
    2.  Watch the **"Top Discussion Topics"** chart. It will instantly update to show you *exactly* which categories (e.g., "shipping") are driving the most complaints.

---

### 2. Tab: Aspect Analysis (The "Specific" Problem)

This tab helps you understand the "why" in even more specific detail.

* **Word Cloud:** This cloud shows the *granular* and *specific* phrases customers mentioned, based on the "Aspects" you provided (e.g., `slow delivery`, `good quality`). Thanks to the backend logic, "good quality" is correctly counted as one phrase, not two separate words.

* **💡 PRO-TIP (Action):**
    1.  Filter for **"NEGATIVE"** sentiment and the **"shipping"** topic in the dropdowns above.
    2.  The Word Cloud will now show you the *exact reason* shipping is a problem. You'll see large phrases like **"slow_delivery"** or **"damaged_box"**, telling you exactly what to fix.

---

### 3. Tab: Discovered Themes (The "Unknown Unknowns")

This is the most advanced AI analysis. This table **ignores** your predefined categories and uses **BERTopic** to find *hidden*, emergent themes and topics of conversation across the entire dataset.

* **💡 PRO-TIP (Action):**
    Look for high-count topics you weren't actively tracking. You might discover that (for example) "Topic 2" has 150 reviews with keywords like `comfort, soft, fabric`. This tells you that "fabric comfort" is a major conversation driver, even if it wasn't one of your initial categories.

* **How to Read This Table:**
    * **Topic:** The ID for the theme. **Topic -1 (Outliers)** is a "junk" category for all unique reviews that don't fit into a larger theme. **You should always ignore Topic -1.**
    * **Count:** The number of reviews in the dataset that belong to this theme.
    * **Name:** A short, auto-generated name for the topic based on its keywords (e.g., `_dress_size_fit_`).
    * **Representation:** The top 10 keywords that best describe the theme. This is the most important column for understanding what the topic is about.
    * **Representative_Docs:** An example of a real review from this group to give you full context.

---

### 4. Tab: Data Explorer

This is the raw, fully enriched data table. Use the filters at the top to find and read specific reviews that match your criteria.
        """)
    
    # Load data from S3 Gold (cached)
    df = load_gold_data(job_id)
    topic_info_df = load_topic_info(job_id)

    if not df.empty:
        st.subheader("Filters")
        filter_cols = st.columns(2)
        
        sentiment_options = ['All'] + sorted(list(df['sentiment'].unique()))
        selected_sentiment = filter_cols[0].selectbox("Filter by Sentiment", options=sentiment_options)
        
        topic_options = ['All'] + sorted(list(df['zero_shot_topic'].unique()))
        selected_topic = filter_cols[1].selectbox("Filter by Topic", options=topic_options)
        
        # Apply filters
        filtered_df = df.copy()
        if selected_sentiment != 'All':
            filtered_df = filtered_df[filtered_df['sentiment'] == selected_sentiment]
        if selected_topic != 'All':
            filtered_df = filtered_df[filtered_df['zero_shot_topic'] == selected_topic]
        
        if filtered_df.empty:
            st.warning("No data matches the selected filters.")
            return
            
        st.subheader("Key Metrics")
        cols = st.columns(3)
        cols[0].metric("Total Reviews Analyzed (Filtered)", f"{len(filtered_df):,}")
        
        if 'sentiment' in filtered_df.columns:
            positive_percentage = (filtered_df['sentiment'] == 'POSITIVE').mean() * 100
            cols[1].metric("Positive Sentiment", f"{positive_percentage:.1f}%")

        if 'rating' in filtered_df.columns and filtered_df['rating'].notna().any():
            avg_rating = filtered_df['rating'].mean()
            cols[2].metric("Average Rating", f"{avg_rating:.2f} ★")
        else:
            cols[2].metric("Average Rating", "N/A")

        # --- Dashboard Tabs ---
        tab1, tab2, tab3, tab4 = st.tabs(["Sentiment & Topics", "Aspect Analysis", "Discovered Themes (BERTopic)", "Data Explorer"])

        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Sentiment Distribution")
                if 'sentiment' in filtered_df.columns:
                    fig = px.pie(filtered_df, names='sentiment', hole=0.3, color='sentiment', 
                                 color_discrete_map={'POSITIVE':'#2ca02c', 'NEGATIVE':'#d62728', 'ERROR':'grey'})
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("What are people talking about?")
                if 'zero_shot_topic' in filtered_df.columns:
                    topic_counts = filtered_df['zero_shot_topic'].value_counts().reset_index()
                    fig2 = px.bar(topic_counts.head(10), y='zero_shot_topic', x='count', 
                                  title='Top 10 Discussion Topics', orientation='h')
                    fig2.update_layout(yaxis={'categoryorder':'total ascending'})
                    st.plotly_chart(fig2, use_container_width=True)

        with tab2:
            st.subheader("Aspect-Based Word Cloud")
            if 'aspects' in filtered_df.columns and filtered_df['aspects'].nunique() > 1:
                # This info message is now correct
                st.info("Showing the most frequently mentioned aspect-sentiment pairs.")
                
                # 1. Clean the 'aspects' series: remove scores (e.g., "(0.90)") and N/A values
                cleaned_aspects = filtered_df['aspects'] \
                                    .str.replace(r' \([^)]*\)', '', regex=True) \
                                    .dropna() \
                                    .replace(["N/A", "PREDICTION_ERROR"], "")

                # 2. Create a list of all individual aspect phrases by splitting by comma and exploding
                all_aspects_list = cleaned_aspects.str.split(', ').explode()

                # 3. Clean up any extra whitespace or empty strings
                all_aspects_list = all_aspects_list.str.strip().replace("", pd.NA).dropna()

                # 4. Count the frequency of each unique phrase (e.g., {"good quality": 10, "slow delivery": 5})
                aspect_frequencies = Counter(all_aspects_list)

                if aspect_frequencies:
                    # 5. Generate the WordCloud from frequencies.
                    wordcloud = WordCloud(width=800, height=400, 
                                          background_color='white', 
                                          colormap='viridis'
                                         ).generate_from_frequencies(aspect_frequencies)
                    
                    # 6. Display the plot
                    fig, ax = plt.subplots()
                    ax.imshow(wordcloud, interpolation='bilinear')
                    ax.axis('off')
                    st.pyplot(fig)
                else:
                    st.info("No aspects found for the selected filters.")
                

            else:
                st.info("No aspect data available.")
        
        with tab3:
            st.subheader("Discovered Themes (BERTopic)")
            st.info("These are hidden themes discovered by the AI, along with their keywords (Topic -1 = outliers).")
            
            if not topic_info_df.empty:
                # Show the table with the keywords
                st.dataframe(topic_info_df, use_container_width=True)
            else:
                st.info("No BERTopic theme info file was found for this job.")
                
        with tab4:
            st.subheader("Explore All Data")
            st.info("Raw data for the selected filters.")
            st.dataframe(filtered_df, use_container_width=True)
    else:
        st.warning("The final data file is empty or could not be loaded. Please wait for the job to complete or check the Stitcher Lambda logs.")


# --- 7. Main App Router ---
st.sidebar.title("ReviewLens AI")
page_options = ['Upload', 'Monitor Job', 'Results']

# This logic controls the navigation
try:
    current_page_index = page_options.index(st.session_state.page)
except ValueError:
    current_page_index = 0
    st.session_state.page = 'Upload'

page_selection = st.sidebar.radio(
    "Navigation",
    page_options,
    index=current_page_index
)

# Detect if the user clicked a different page in the sidebar
if page_selection != st.session_state.page:
    st.session_state.page = page_selection
    st.rerun()

# --- Render the selected page ---
if st.session_state.page == 'Upload':
    render_upload_page()
elif st.session_state.page == 'Monitor Job':
    render_monitoring_page()
elif st.session_state.page == 'Results':
    render_results_page()