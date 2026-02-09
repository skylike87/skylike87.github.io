# 🚀 Automated Quant-IT Odyssey: The Art of Agent Orchestration

This repository is more than a blog—it is a live laboratory where **7+ years of professional expertise** (5 years in Java Development & 2 years in Quality Assurance) converge with the future of AI.

In an era where "just coding" is no longer enough, I focus on **Orchestrating AI Agents** to build resilient, high-quality autonomous systems.

## 🤖 The Orchestration Engine: Dual-LLM Pipeline

Modern engineering is about choosing the right tool for the right task. My blog is powered by a strategic, multi-layered AI pipeline:

* **Logic & Intent Handler (Llama 3.1 8B)**: Leveraging its speed for intent recognition and initial data validation. This reflects my **QA background**—ensuring every signal is valid before processing.
* **Content Architect (Claude 3.5/3.7 Sonnet)**: Transforming validated signals into high-fidelity technical posts, ensuring the "Definition of Done" is met with professional-grade prose.

---

## 🛠️ Technical Arsenal

### **Automation & Orchestration**

* **The Brain**: Python-based Orchestrator using a Strategy Pattern for modular LLM integration.
* **The Heart**: macOS `launchd` + Robust **Zsh Bootstrapper** (`trigger.sh`) featuring **Atomic Locking** and **Fail-Fast** error handling.
* **Quality & Stability**: Integrated QA principles—automated state tracking via SQLite3 and idempotent workflow design.

### **Blog Infrastructure**

* **Jekyll Chirpy Theme**: Optimized for technical readability and SEO.
* **CI/CD**: GitHub Actions for automated "Daily-Signal" generation and site deployment.

---

## ⚙️ The Workflow: From Signal to Publication

1. **Signal**: A GitHub Action generates a "Daily-Signal" issue every morning.
2. **Input**: I provide raw technical insights or "struggle logs" as comments.
3. **Trigger**: Local `launchd` polling detects the signal  initiates the **Orchestrator**.
4. **Processing**: **Llama 8B** validates the intent  **Claude Sonnet** crafts the narrative  Auto-PR.
5. **Quality Check**: I review the PR (Final QA) and merge to deploy.

---

> "The future belongs to those who can orchestrate the symphony of AI agents, not just those who can write the notes."

### 📬 Connect with Me

* **Blog**: [skylike87.github.io](https://skylike87.github.io)
