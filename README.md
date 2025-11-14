# ✅ ReviewLens AI — Automated Review Analysis Pipeline

[![AWS Serverless](https://img.shields.io/badge/AWS-Serverless-FF9900.svg?logo=amazonaws)](https://aws.amazon.com/serverless/)
[![Infrastructure as Code](https://img.shields.io/badge/IaC-Terraform-7B42BC.svg?logo=terraform)](https://www.terraform.io/)
[![Frontend](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B.svg?logo=streamlit)](https://streamlit.io/)

> An end-to-end, serverless, event-driven AI architecture on AWS to transform customer reviews into actionable business insights. Fully deployed and managed with Infrastructure as Code (Terraform).

---

## 🌐 Interactive Demo

Test the complete system deployed on Streamlit Cloud. You can upload your own CSV file or use the built-in sample data.

🔗 **[Launch ReviewLens AI Demo](https://reviewlens-ai-showcase.streamlit.app/)** 📤

---

## 🎯 The Business Problem (Why This Project?)

Every modern company collects reviews, but this goldmine of data often sits unused.

* 📈 **Data Overload:** Manually reading and tagging thousands of reviews is impossible. Valuable feedback is lost.
* 📉 **Hidden Problems:** Managers know *that* sentiment is dropping, but not *why*. Is it `price`, `shipping`, or `fabric quality`?
* ❌ **Missed Opportunities:** Companies fail to identify what customers love (to double-down on) or what's driving them away (to fix immediately).

I designed ReviewLens AI to demonstrate how a modern, serverless AI architecture can transform this "noise" into a clear, strategic asset.

---

## ⚡ The Transformation: From Raw Data to Actionable Insight

ReviewLens AI ingests a simple CSV and enriches it with four layers of insight, turning raw text into an analysis-ready data asset.

### **BEFORE**
A simple CSV file with unstructured text:
| Review |
| :--- |
| "I love this dress! The fabric is so soft, but the shipping was terribly slow." |
| "The price is great, but the pants fit is weird and the zipper feels cheap." |

### **AFTER**
A rich Parquet file, ready for any BI tool or dashboard:

| full\_review\_text | sentiment | zero\_shot\_topic | aspects | bertopic\_id |
| :--- | :--- | :--- | :--- | :--- |
| "I love this dress! The fabric..." | `POSITIVE` | `quality` | `fabric (POSITIVE)`, `shipping (NEGATIVE)` | 7 |
| "The price is great, but the..." | `NEGATIVE` | `price` | `price (POSITIVE)`, `fit (NEGATIVE)`, `zipper (NEGATIVE)` | 14 |

---

## 🗺️ System Architecture
![Architecture Diagram](docs/reviewlens_ai_architecture.png)

### Medallion layers
The project follows the Medallion Architecture approach, structuring data into three distinct layers:

* **Bronze:** for storing raw, ingested data.
* **Silver:** for cleaned, processed, and transformed data.
* **Gold:** for business-ready datasets.

This layered design improves data quality, reliability, and usability. **[Full methodology here](https://github.com/kevindellapiazza/data-foundations-for-ai)**
---

## 🚀 How It Works (Technical Breakdown)

1.  **Ingestion & Orchestration:** A user uploads a CSV on the **Streamlit** frontend. The app attaches the column mapping (e.g., `{"full_review_text": "Review_Column"}`) as S3 `Metadata` and uploads the file to the **Bronze Bucket**.
    * The S3 event triggers the **`splitter-lambda`** (Docker).
    * The Lambda validates the metadata, uses the file's **ETag** as an idempotent `job_id`, and registers the job in **DynamoDB**.
    * It splits the CSV into small batches and starts a parallel **AWS Step Function** execution *for each batch*.

2.  **Parallel AI Analysis (Step Functions):** The State Machine orchestrates a 3-stage AI pipeline for each batch:
    * **`sentiment-lambda`**: Performs overall sentiment analysis (`POSITIVE`/`NEGATIVE`).
    * **`zeroshot-lambda`**: Classifies into dynamic topics (e.g., `price`, `quality`), using default labels or provided by the user.
    * **`absa-lambda`**: Conducts Aspect-Based Sentiment Analysis for granular insights (e.g., `fabric (NEGATIVE)`), using default labels or provided by the user.
    * The final Lambda saves the enriched batch to the **Silver Bucket** and atomically increments a counter in DynamoDB.

3.  **Job Monitoring (API Gateway):** The frontend provides a seamless monitoring experience by calling two lightweight API endpoints (deployed as `.zip`):
    * `GET /find-job/{upload_id}`: Hits the **`find-job-lambda`**, which queries a DynamoDB GSI to find the *real* `job_id` (the ETag) associated with the frontend's upload ID.
    * `GET /status/{job_id}`: Once found, the frontend polls this endpoint (hitting the **`status-checker-lambda`**) to get the job's progress percentage.

4.  **Finalization & Discovery:** Clicking "Generate Final Report" on the frontend triggers a `POST /stitch` call.
    * This invokes the **`stitcher-lambda`** (Docker), which reads and merges all intermediate Parquet files from the Silver Bucket.
    * It runs a final **BERTopic** analysis on the entire dataset to discover hidden themes.
    * It saves the final file to the **Gold Bucket**, cleans up the Silver Bucket, and sets the DynamoDB status to `COMPLETED`.

---

## ✨ Key Architectural Features (For Recruiters)

1.  **100% Infrastructure as Code (IaC):** The entire cloud infrastructure (S3, DynamoDB, ECR, Step Functions, API Gateway,SQS and all 7 Lambdas) is defined and managed with **Terraform**.
2.  **Scalable "Fan-Out" Orchestration:** Using **Step Functions** to parallelize the analysis ("fan-out") makes the architecture massively scalable, resilient (with built-in `Retry` and `Catch`), and cost-efficient.
3.  **Hybrid Deployment Strategy (Docker vs .zip):** This project demonstrates advanced deployment trade-offs:
    * **Docker:** Used for the 5 complex AI/data Lambdas (like `absa` and `stitcher`) to manage heavy dependencies (`torch`, `pandas`, `bertopic`).
    * **.zip:** Used for the 2 lightweight API Lambdas (`find-job`, `status-checker`) to achieve **minimal cold starts** (milliseconds) and near-zero cost.
4.  **MLOps Optimization ("Baked-in" Models):** The AI Lambda Docker images use a multi-stage build to "bake-in" the Transformer models. By setting `HF_HOME` to a local path (`/var/task/model_cache`), the model is loaded instantly from memory, **eliminating model download time at cold start**.
5.  **Robust & Resilient by Design:**
    * **Idempotent Pipeline:** Using the file ETag as the `job_id` prevents duplicate processing and costs for the same file.
    * **Dead Letter Queue (DLQ):** All AI Lambdas are connected to an SQS queue. If a batch fails (e.g., "poison pill" data), it's isolated for inspection without stopping the entire job.
    * **Security:** IAM policies use the "Principle of Least Privilege" for each Lambda, and all S3 buckets are 100% private.

---

## 🚀 Performance, Trade-offs, & Scalability

This project is intentionally configured for **minimum cost (scale-to-zero)**, not raw processing speed. The current demo performance (e.g., cold starts, processing time) is a direct result of these deliberate cost-saving trade-offs.

For a production environment requiring high-speed or massive volume, the architecture is designed to scale in the following ways:

* **1. Eliminating Cold Starts:** For a low-latency API, **Provisioned Concurrency** (warm-ups) would be enabled on all 5 Docker-based Lambdas. This keeps the containers "hot" and **eliminates cold starts** entirely.

* **2. Increasing Speed (vCPU):** The AI Lambdas are currently set to `3008MB` (the maximum for this new account). Since Lambda allocates vCPU power proportionally to memory, **raising the service quota to 10240MB (10 GB)** would provide ~6 vCPUs and drastically cut inference time.

* **3. Scaling Concurrency:** The current 10-Lambda concurrency limit creates an artificial bottleneck (throttling). **Raising the account quota to 1000** allows the "fan-out" pattern to run hundreds of batches in parallel as intended.

* **4. Evolving the Compute Layer (The MLOps Scalability Path):**
    This architecture can evolve in two distinct ways depending on business needs:

    * **For Massive Batch Processing (10M+ rows):** The "fan-out" pipeline (`splitter`, `sentiment`, `zeroshot`, `absa`) scales perfectly. The only bottleneck is the `stitcher-lambda`, which cannot load 10M rows into 10GB of RAM. The solution is to refactor the `stitcher-lambda` to *trigger* an **AWS Batch** or **Fargate** job. This moves the heavy compute to a dedicated, long-running container (e.g., with 128GB of RAM) to perform the final aggregation and BERTopic analysis.

    * **For High-Throughput Real-Time API:** If the goal was sub-second responses (instead of batch processing), the models would be deployed to dedicated **AWS SageMaker Endpoints**. The API Gateway would invoke these endpoints directly, providing auto-scaling, high-performance inference completely separate from this batch architecture.

---

## 🧠 Skills Demonstrated

* **Infrastructure as Code (IaC):** Designed and deployed a complex, multi-service cloud architecture from scratch using **Terraform** to manage state, dependencies, and configuration.
* **Serverless & Event-Driven Architecture:** Built a robust, asynchronous, and scalable pipeline using S3 event triggers, API Gateway, SQS, Step Functions, and Lambda.
* **MLOps & AI Deployment:** Containerized and deployed **4 distinct NLP models** in a resource-constrained serverless environment (AWS Lambda), solving complex challenges like the 10GB size limit, read-only filesystems (`HF_HOME`), and C++ build dependencies (`hdbscan`).
* **Data Engineering:** Implemented a "fan-out" parallel processing workflow and designed a **Medallion Data Architecture** (Bronze/Silver/Gold) with optimized Parquet storage and merge (`awswrangler`).
* **Backend & API Development:** Wrote 7 Python microservices (Lambdas) and a supporting REST API (API Gateway, DynamoDB GSI) to enable a seamless, decoupled frontend experience.
* **Full-Stack Prototyping:** Developed a polished **Streamlit** application that acts as a professional "front door" to the complex backend.
* **Cloud Security & Robustness:** Applied the principle of least privilege (IAM), secured S3 buckets, and built a resilient system with **idempotency** (ETag `job_id`) and **Dead Letter Queues (DLQ)**.

---

## 💰 Cloud Cost Estimate (1 Million Reviews / Month)

This system is optimized for extreme affordability, even at high scale.
All costs are based on the **eu-west-1 (Ireland)** region (October 2025).

| Service | Approx. Cost | Description |
| :--- | :--- | :--- |
| **Lambda (AI Compute)** | $8.82 | ~530,000 GB-seconds (post-free-tier) for the 3 AI models (`sentiment`, `zeroshot`, `absa`) processing 5,000 batches. |
| **Step Functions** | $0.28 | 15,000 state transitions (3 steps x 5,000 batches). |
| **S3 Storage** | ~$0.03 | ~1.2 GB of total storage across Bronze, Silver, and Gold. |
| **Lambda (Requests)** | ~$0.01 | ~15,000 total requests for all functions (first 1M are free). |
| **DynamoDB** | $0.00 | ~5,000 writes + ~30 reads. Well within the "pay-per-request" free tier. |
| **API Gateway** | $0.00 | ~30 API requests. Well within the free tier. |
| **SQS (DLQ)** | $0.00 | $0.00 (assuming a low failure rate). |
| **TOTAL** | **~$9.14 / month** | For 1 million reviews analyzed. |

> 🔍 **Almost 100% of the cost is for the AI computation itself.** The entire supporting infrastructure (storage, database, API, orchestration) costs less than $0.50 per month.

---

## 🔐 Security (Best Practices Implemented)

| Layer | Practice |
| :--- | :--- |
| **S3** | All data buckets (Bronze, Silver, Gold, Deploy) are **100% private** with `block_public_access` enabled. Encryption at-rest (SSE-S3). |
| **IAM** | **Principle of Least Privilege:** Every Lambda has its own unique IAM role with surgical permissions. (e.g., `find-job-lambda` can *only* query the GSI; `absa-lambda` can *only* write to Silver and update DynamoDB). |
| **API Gateway** | **CORS is handled at the Gateway level** (not by Lambda) for better security and performance, allowing calls only from authorized domains and for `GET`/`POST` methods. |
| **Data Flow** | **Idempotent** pipeline (ETag `job_id`) prevents duplicates. No sensitive data (review content) is logged to CloudWatch. |
| **Error Handling** | **Dead Letter Queue (DLQ)** configured for all AI Lambdas, isolating "poison pill" data without halting the entire process. |
| **Secrets** | All frontend secrets (AWS Keys, API URL) are managed via `st.secrets` and are never hardcoded. |

> ✅ Compliant with the **AWS Well-Architected Framework** pillars (Security, Cost Optimization, Performance Efficiency, Reliability).

---

## 📦 Backend Deployment (For Technical Reviewers)

The entire infrastructure is defined in the `.tf` files in the `terraform/` folder.

#### Prerequisites
* AWS Account & IAM User (with AWS CLI credentials configured)
* AWS CLI
* Terraform CLI
* Docker Desktop
* Python 3.11+

#### Deployment Steps

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/kevindellapiazza/reviewlens-ai.git](https://github.com/kevindellapiazza/reviewlens-ai.git)
    cd reviewlens-ai
    ```

2.  **Build & Push Docker Images (5 Lambdas):**
    *(Repeat for `01-splitter`, `02-sentiment`, `03-zeroshot`, `04-absa`, `05-stitcher`)*
    ```bash
    # Example for one Lambda:
    cd src/01-splitter-lambda
    docker build -t reviewlens-01-splitter-repo .
    docker tag reviewlens-01-splitter-repo:latest <aws-account-id>[.dkr.ecr.eu-west-1.amazonaws.com/reviewlens-01-splitter-repo:latest](https://.dkr.ecr.eu-west-1.amazonaws.com/reviewlens-01-splitter-repo:latest)
    docker push <aws-account-id>[.dkr.ecr.eu-west-1.amazonaws.com/reviewlens-01-splitter-repo:latest](https://.dkr.ecr.eu-west-1.amazonaws.com/reviewlens-01-splitter-repo:latest)
    ```

3.  **Package .zip Lambdas (2 Lambdas):**
    ```bash
    # Package the find-job-lambda
    cd src/find-job-lambda
    Remove-Item -Path deployment.zip -ErrorAction SilentlyContinue
    Compress-Archive -Path main.py -DestinationPath deployment.zip

    # Package the status-checker-lambda
    cd src/api-status-checker-lambda
    Remove-Item -Path deployment.zip -ErrorAction SilentlyContinue
    Compress-Archive -Path main.py -DestinationPath deployment.zip
    ```

4.  **Deploy the Infrastructure (Terraform):**
    ```bash
    cd terraform
    terraform init
    terraform apply
    ```
    This command will provision all 50+ AWS resources, connect them, and deploy the code.

---

## 🔧 Tools & Technologies

* **IaC:** Terraform
* **Compute:** AWS Lambda (Python 3.11/3.12, Docker & .zip)
* **AI / NLP:** Hugging Face `transformers`, `bertopic`, `sentence-transformers`
* **Orchestration:** AWS Step Functions
* **Storage:** Amazon S3 (Medallion Architecture), Amazon ECR
* **Database:** Amazon DynamoDB (with Global Secondary Index)
* **API / Triggers:** Amazon API Gateway (HTTP API v2), S3 Event Notifications
* **Error Handling:** Amazon SQS (Dead Letter Queue)
* **Frontend:** Streamlit

---

## 🛡️ License & Project Use

This project is published for educational and portfolio purposes. All code was written by **Kevin Della Piazza**.

**For Recruiters & Hiring Managers:**
* ✅ You are encouraged to **clone, test, and review** this repository as part of the hiring process.

**For Other Developers:**
* ✅ You are welcome to **read and learn** from this code.
* ❌ You **may not** copy, fork, or reuse this code in your own portfolios or for commercial purposes.

**All rights reserved © Kevin Della Piazza**