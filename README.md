# CarbonWise 

CarbonWise is an intelligent, data-driven Carbon Footprint Awareness Platform designed to help individuals monitor their environmental impact, track daily activities, and adopt eco-friendly habits. 

Powered by **Google Gemini** and built as an autonomous AI agent, CarbonWise doesn't just calculate emissions—it provides hyper-personalized, actionable mitigation strategies to help users actively reduce their carbon footprint.

---

## 🚀 Key Features

* **Smart Carbon Calculator:** Seamlessly estimates carbon footprints across key daily domains:
    *  **Transport:** Analyzes commuting habits (e.g., petrol vehicle mileage vs. public transit).
    * **Energy:** Tracks monthly electricity utilization (kWh) and targets phantom loads.
    *  **Diet:** Evaluates dietary choices (e.g., vegetarian optimization) and calculates food miles.
    *  **Waste:** Monitors weekly non-recycled waste generation and highlights diversion metrics.
* **Dynamic Visual Dashboard:** Features interactive donut charts and dynamic real-time progress bars to immediately expose major emission drivers.
* **Comparative Benchmarking:** Maps user scores against regional and global net-zero targets to provide immediate environmental context.
* **Behavioral Gamification (Pledge System):** Allows users to commit to specific lifestyle changes (e.g., *“Set AC to 24°C”*) and displays running aggregations of total projected $CO_2$ savings.
* **Interactive AI Agent:** A conversational workspace powered by Gemini to answer complex sustainability questions and suggest tailored reduction plans.

---

##  Architecture & Google Cloud Stack

CarbonWise is engineered using enterprise-grade, serverless Google Cloud technologies to ensure rapid deployment, auto-scaling, and secure data handling:

* **Orchestration:** Built with the **Google Cloud Agent Development Kit (ADK)** to manage the AI agent's logic, enabling tool-use and structured reasoning.
* **Core LLM:** Powered by **Vertex AI / Gemini API** for generating contextual, highly verified environmental advice and processing custom user prompts.
* **Compute & Hosting:** Containerized via Docker and fully deployed on **Google Cloud Run**, delivering a scalable, serverless production environment.
* **CI/CD Pipeline:** Integrated with **Google Cloud Build** to enable continuous integration and automated deployment flows directly from GitHub.
* **Database & Storage:** Backed by **Cloud Firestore (NoSQL)** to maintain persistent user states, profiles, and historical tracking logs.
* **Identity Management:** Uses **Firebase Authentication** to provide seamless, secure Google Sign-In capabilities.

---

##  Local Development Setup

### Prerequisites
* Node.js (v18+) or Python (depending on your specific backend flavor)
* Docker Desktop
* Google Cloud SDK configured with your project credentials

---

## 🛠️ Code Quality

CarbonWise enforces strict coding guidelines and best practices to ensure high maintainability, readability, and reliability:

- **Modular Architecture:** Core logic is cleanly segregated:
  - `app.py`: Acts as a controller handling web/API routes (each route handler and function is strictly capped under 25 lines of code).
  - `carbon_calculator.py`: Pure deterministic engine calculating category emissions and comparing against regional benchmarks.
  - `utils.py`: Reusable utility functions covering rate limiting, cache checks, payload schemas, and Gemini API calls.
- **Type Annotations:** PEP 484 type hints are fully integrated across all function signatures to enable static type analysis.
- **Documentation Standards:** Every function is fully documented using Google-Style Docstrings featuring explicit `Args`, `Returns`, and `Raises` sections.
- **Linting Rules:** Configured via `.flake8` (limiting max-line-length to 100) to ensure uniform style guidelines.


