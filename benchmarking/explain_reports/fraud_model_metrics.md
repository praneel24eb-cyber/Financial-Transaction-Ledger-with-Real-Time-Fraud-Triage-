# Isolation Forest Fraud Model Evaluation Report

**Evaluation Date:** October 2026  
**Model Architecture:** Unsupervised Isolation Forest (100 estimators, 5% expected contamination)  
**Triage Thresholds:**
- Risk Score < 50: **APPROVE** (Normal)
- Risk Score 50–80: **REVIEW** (Human Analyst Queue)
- Risk Score > 80: **ROLLBACK** (Immediate Freeze)

---

## 1. Summary Metrics

| Metric | Score | Industry Benchmark | Compliance Status |
|---|---|---|---|
| **Accuracy** | 99.70% | > 95.0% | Meets Requirement |
| **Precision** | 93.98% | > 75.0% | Meets Requirement |
| **Recall (Sensitivity)** | 100.00% | > 85.0% | Meets Requirement |
| **F1-Score** | 0.9690 | > 0.80 | High Performance |
| **ROC-AUC** | 1.0000 | > 0.90 | High Discrimination |
| **False Positive Rate (FPR)** | 0.32% | < 3.0% | Low Customer Friction |

---

## 2. Confusion Matrix

```
                      Predicted Normal    Predicted Fraud / Review
Actual Normal (y=0)          4984                     16
Actual Fraud  (y=1)             0                    250
```

- **True Positives (TP):** 250 anomalous transactions successfully flagged.
- **False Positives (FP):** 16 normal transfers routed for analyst verification.
- **True Negatives (TN):** 4984 normal transfers approved with zero delay.
- **False Negatives (FN):** 0 fraud attempts missed.

---

## 3. Analysis & Key Takeaways

1. **Low False Positive Rate (0.32%)**: Prevents excessive analyst queue backlog and minimizes legitimate customer disruptions.
2. **High Recall (100.00%)**: Detects the vast majority of anomalous high-amount bursts, foreign logins, and rapid velocity spikes before funds leave the core ledger.
3. **Fail-Safe Robustness**: In case of ML engine latency or timeout, the deterministic rule-based fallback safeguards the ledger by flagging extreme transfers (>₹50,000 or >5 velocity) as `REVIEW`.
