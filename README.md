'''
# ✅ ReviewLens AI — Automated Review Analysis Pipeline

[![Infrastructure as Code](https://img.shields.io/badge/IaC-Terraform-7B42BC.svg)](https://www.terraform.io/)
[![Frontend](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B.svg)](https://streamlit.io/)
[![Backend](https://img.shields.io/badge/Backend-AWS%20Lambda-FF9900.svg)](https://aws.amazon.com/lambda/)

> An end-to-end, serverless AI pipeline on AWS for transforming customer reviews into actionable business insights. This repository contains the public-facing **Streamlit frontend** and **project documentation**.

---

## 🌐 Interactive Demo

Test the live application, deployed on Streamlit Cloud, right here. You can upload your own CSV file or use the built-in "Demo Mode" to see a pre-analyzed report.

🔗 **[Launch ReviewLens AI Demo](https://your-streamlit-app-url-goes-here.streamlit.app/)** 📤

---

## 📌 Project Overview

ReviewLens AI is a production-grade, event-driven system that automates the multi-layer analysis of customer reviews. The **frontend** (in this repository) is a user-friendly Streamlit app. The **backend** (held in a private repository) is an event-driven architecture defined with **Terraform**.

This project solves a critical business problem by transforming unstructured customer feedback into a **multi-layered, queryable, and analytics-ready data asset**. The pipeline extracts sentiment, identifies key topics, performs aspect-based analysis, and discovers hidden themes, turning raw text into a strategic tool for decision-making.

---

## 🎯 Why This Matters

* 📈 **Data Overload:** Businesses collect thousands of customer reviews, but this goldmine of data sits unread, and valuable feedback is lost.
* 📉 **Hidden Problems:** Companies don't know *why* their sentiment score is dropping. Are customers angry about `price`, `shipping`, or a `fabric quality` issue?
* ❌ **Missed Opportunities:** Businesses fail to see what customers love (to double down on) or what's driving them away (to fix immediately).

As an engineer, I designed ReviewLens AI to showcase how a modern, serverless AI architecture can transform this "noise" into a clear, strategic asset.

---

## ⚡ The Result

A system that is:

* ✅ **Actionable:** Doesn't just give a rating, but answers *why*. It flags specific topics (e.g., `shipping`) and granular aspects (e.g., `delivery time (NEGATIVE)`).
* ✅ **Massively Scalable:** The serverless, fan-out architecture can process millions of reviews with the same efficiency.
* ✅ **Cost-Effective:** Runs entirely on serverless components. You pay *only* for the analysis performed, not for idle servers.
* ✅ **Fully Automated:** A user uploads a file, and the final, enriched data appears in the Gold layer, ready for analytics.

---

## 💎 The Transformation: From Raw Data to Actionable Insight

ReviewLens AI ingests a simple CSV file and enriches it with four new layers of AI-generated data.

### **BEFORE**
A simple CSV file with one column of unstructured text:
| Review Text |
| :--- |
| "I love this dress! The fabric is so soft, but the shipping was terribly slow." |
| "The price is great, but the pants fit is weird and the zipper feels cheap." |

### **AFTER**
A rich, queryable data asset (a Parquet file) ready for any BI tool or database:

| full\_review\_text | sentiment | zero\_shot\_topic | aspects | bertopic\_id |
| :--- | :--- | :--- | :--- | :--- |
| "I love this dress! The fabric..." | `POSITIVE` | `quality` | `fabric (POSITIVE)`, `shipping (NEGATIVE)` | 7 |
| "The price is great, but the..." | `NEGATIVE` | `price` | `price (POSITIVE)`, `fit (NEGATIVE)`, `zipper (NEGATIVE)` | 14 |

---

## 🗺️ System Architecture

This project follows the **Medallion Architecture** (Bronze, Silver, Gold layers) and is built on a 100% serverless, event-driven model.

*(Note: The full `terraform/` infrastructure code is in the private backend repository. The core R&D for this architecture is available in the [Model Development Notebook](./notebooks/model_development.ipynb).)*

![Architecture Diagram](https"https://i.imgur.com/YOUR_ARCHITECTURE_IMAGE_URL.png")

To learn more about the data methodology, see my public repository on **[AI Data Foundations](https://github.com/kevindellapiazza/data-foundations-for-ai)**.

---

## 🚀 How It Works (Step-by-Step)

1.  **Ingestion & Orchestration (Frontend -> Splitter):** A user uploads a CSV file via the **Streamlit** frontend, which attaches a JSON column mapping (e.g., `{"full_review_text": "Review_Column"}`) as S3 `Metadata`. This S3 event triggers the **`splitter-lambda`** (Docker), which validates the file, uses its ETag as an idempotent `job_id`, registers the job in **DynamoDB**, and starts a parallel **Step Function** execution for each batch of reviews.

2.  **Parallel AI Analysis (Step Functions):** The Step Function orchestrates a 3-step AI pipeline for every batch:
    * **`sentiment-lambda`**: Performs overall sentiment analysis (`POSITIVE`/`NEGATIVE`).
    * **`zeroshot-lambda`**: Classifies the review into predefined topics (`price`, `quality`, etc.).
    * **`absa-lambda`**: Conducts Aspect-Based Sentiment Analysis to find granular insights (e.g., `fabric (NEGATIVE)`).
    * Each successful batch is saved as a Parquet file in the **Silver Bucket**.

3.  **Seamless Job Monitoring (API Gateway):** The Streamlit frontend provides a "zero-tech" monitoring experience by:
    * First, calling a `GET /find-job/{upload_id}` endpoint. This hits the **`find-job-lambda`** (.zip) which queries a DynamoDB GSI to find the *real* `job_id` (the ETag).
    * Then, repeatedly calling `GET /status/{job_id}`, which hits the **`status-checker-lambda`** (.zip) to get the job's progress from DynamoDB.

4.  **Finalization & Discovery (Stitcher):** Once the job is processed, the user clicks "Generate Final Report" in the frontend, which calls `POST /stitch`. This invokes the **`stitcher-lambda`** to merge all batch files, run a final `BERTopic` analysis to discover hidden themes, and save the final report to the **Gold Bucket**.

---

## ✨ Key Features & Architectural Highlights

1.  **100% Infrastructure as Code (IaC) with Terraform:** The *entire* backend (S3, DynamoDB, ECR, SQS, Step Functions, API Gateway, 6 Lambdas) is defined in a private Terraform repository.
2.  **Hybrid Lambda Deployment Strategy:** Demonstrates professional trade-offs by using **Docker Containers** for complex AI Lambdas (managing `torch`, `pandas`) and **.zip Packages** for lightweight API helper Lambdas (`find-job`, `status-checker`) to optimize for speed and cost.
3.  **Multi-Layer AI Analysis:** A full-stack AI pipeline that creates a 4-layer "insight funnel": L1 (Sentiment), L2 (Known Topics), L3 (Specific Aspects), and L4 (Hidden Themes).
4.  **Robust & Resilient by Design:** The backend pipeline is **idempotent** (prevents duplicate runs) and uses an **SQS Dead Letter Queue** to ensure one bad review never stops the entire job.
5.  **Seamless Frontend Experience:** This Streamlit app is fully decoupled and uses a "smart polling" system (`/find-job` API) to hide all backend complexity (like ETag job IDs) from the end-user.

---
## 🔐 Lambda Source Code & IaC

To protect the project's intellectual property for commercialization, the full backend source code (`src/`) and infrastructure code (`terraform/`) are held in a **separate private repository**.

Full access is available upon request for technical interviews. Key code samples are available for review here:

🔗 **[View Backend Code Samples](./CODE_SAMPLES.md)**

---

## 🚀 Running the Frontend Demo (Locally)
While the backend requires an AWS account and Terraform deployment, you can run the Streamlit frontend on your local machine to interact with the live demo.

#### Prerequisites
* Python 3.11+
* Git

#### Deployment Steps
1.  **Clone this repository:**
    ```bash
    git clone [https://github.com/kevindellapiazza/reviewlens-ai-showcase.git](https://github.com/kevindellapiazza/reviewlens-ai-showcase.git)
    cd reviewlens-ai-showcase
    ```

2.  **Create a virtual environment:**
    ```bash
    cd dashboard
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create your secrets file:**
    * Create a new folder in the `dashboard` directory named `.streamlit`.
    * Inside `.streamlit`, create a file named `secrets.toml`.
    * Add your AWS credentials and API endpoint (from the backend deployment) to this file:
        ```toml
        # .streamlit/secrets.toml
        AWS_ACCESS_KEY_ID = "YOUR_KEY_HERE"
        AWS_SECRET_ACCESS_KEY = "YOUR_SECRET_HERE"
        AWS_DEFAULT_REGION = "eu-west-1"

        # The API endpoint from your Terraform output
        API_URL = "https://<api-id>.execute-api.eu-west-1.amazonaws.com"
        
        # The exact names of your deployed buckets
        S3_BRONZE_BUCKET = "reviewlens-bronze-bucket-xxxx"
        GOLD_BUCKET_NAME = "reviewlens-gold-bucket-xxxx"
        ```

5.  **Run the app:**
    ```bash
    streamlit run app.py
    ```
    The application will automatically open in your web browser.

---

## 🔧 Tools & Technologies
* **IaC:** Terraform
* **Compute:** AWS Lambda (Python 3.11/3.12 Runtimes & Docker Container Images)
* **AI / NLP:** Hugging Face `transformers`, `pyabsa`, `bertopic`, `scikit-learn`
* **Orchestration:** AWS Step Functions
* **Storage:** Amazon S3 (Medallion Architecture), Amazon ECR
* **Database:** Amazon DynamoDB (with Global Secondary Index)
* **API / Triggers:** Amazon API Gateway (HTTP API), S3 Event Notifications
* **Error Handling:** Amazon SQS (as a Dead Letter Queue)
* **Frontend:** Streamlit

---

## 🧠 Skills Demonstrated
* **Infrastructure as Code (IaC):** Designed and deployed a complete, multi-service cloud architecture from scratch using **Terraform**.
* **Serverless & Event-Driven Architecture:** Built a robust, asynchronous, and scalable pipeline using S3 event triggers, API Gateway, SQS, Step Functions, and Lambda.
* **MLOps & AI Deployment:** Successfully containerized and deployed **4 distinct NLP models** in a resource-constrained serverless environment (AWS Lambda), solving complex challenges like the 10GB size limit, read-only filesystems (`HF_HOME`), and library import conflicts (`PYTHONPATH`).
* **Hybrid Deployment Strategy:** Demonstrated advanced architectural trade-offs by using **Docker** for complex, heavy AI functions and **.zip packages** for lightweight, high-speed API functions.
* **Data Engineering:** Implemented a "fan-out" parallel processing workflow and designed a **Medallion Data Architecture** (Bronze/Silver/Gold) with optimized Parquet storage.
* **Backend & API Development:** Wrote 6 distinct Python microservices (Lambdas) and a supporting REST API (API Gateway, DynamoDB GSI) to enable a seamless frontend experience.
* **Full-Stack Prototyping:** Developed a polished **Streamlit** application that acts as a professional "front door" to the complex backend, demonstrating a strong understanding of product and user experience.
* **Cloud Security & Robustness:** Applied the principle of least privilege with specific IAM roles for each Lambda, secured all S3 buckets, and built a resilient system with **idempotency** and **Dead Letter Queues**.

---

## 🛡️ License & Use
This project is published for educational and portfolio purposes. The frontend and notebook are public, while the backend and IaC source are in a private repository.

All code was written by **Kevin Della Piazza**.

You may:

✅ Read and learn from this project
✅ Run the frontend demo and test the live application
✅ Request full backend source code access for technical interviews

You may not:

❌ Reuse or fork this code for other portfolios, applications, or commercial tools

**All rights reserved © Kevin Della Piazza**
'''