# Implementation Specification: Role-Based Access Control (RBAC) & Fraud UI Gating

## 1. Overview & Objective
This document outlines the implementation plan to resolve two critical architectural discrepancies between the project documentation (`README.md`, `Demo_Script_and_Viva_QA.md`, `frontend_features.txt`) and the current frontend implementation:
1. **Lack of Frontend RBAC**: There is currently no login, session, or role selector in the UI. All pages (`/ui/alerts`, `/ui/audit`, `/ui/benchmarks`) are publicly accessible without authentication or role validation.
2. **Information Leakage in Customer View**: Fraud alerts, ML risk scores (0–100), rule hits, and internal triage decisions are displayed on the default dashboard and accessible to regular customer views, violating the security and customer-facing confidentiality specifications.

---

## 2. Target Roles & Access Matrix

| Feature / UI Route | 👤 Customer (Default) | 🛡️ Fraud Analyst | ⚡ System Admin |
| :--- | :---: | :---: | :---: |
| **Home Dashboard** (`/`) | Filtered (Clean Banking KPI) | Full View (Includes Alert KPI) | Full View |
| **Quick Transfer Form** | Allowed (Customer Status Only) | Allowed | Allowed |
| **Transfer Portal** (`/ui/transfer`) | Allowed (Masked Feedback) | Allowed (Full Feedback) | Allowed |
| **Ledger Statement** (`/ui/history`) | Allowed (Own Statements) | Allowed (All Accounts) | Allowed |
| **Fraud Alerts Queue** (`/ui/alerts`) | ❌ **Hidden & Blocked (403)** | ✅ **Allowed** | ✅ **Allowed** |
| **Audit Hash-Chain** (`/ui/audit`) | ❌ **Hidden & Blocked (403)** | ❌ **Hidden & Blocked (403)** | ✅ **Allowed** |
| **DBMS Benchmarks** (`/ui/benchmarks`)| ❌ **Hidden & Blocked (403)** | ❌ **Hidden & Blocked (403)** | ✅ **Allowed** |
| **Internal ML Score Display** | ❌ **Masked / Hidden** | ✅ **Visible (0–100)** | ✅ **Visible (0–100)** |
| **Database Seed / Reset API** | ❌ **Blocked (403)** | ❌ **Blocked (403)** | ✅ **Allowed** |

---

## 3. Architecture & Technical Design

### A. Role State & Session Management
Instead of requiring heavy user authentication with password hashes (which complicates live evaluation walkthroughs), a **Cookie-Backed Role Session Switcher** will be used:
1. **Cookie Name**: `user_role`
2. **Allowed Values**: `customer` (default), `analyst`, `admin`.
3. **Endpoint**: `POST /api/v1/auth/role` accepts `{ "role": "<customer|analyst|admin>" }` and sets an `HttpOnly=False`, `SameSite=Lax` cookie.
4. **FastAPI Request Extraction**:
   - Page routes inspect `request.cookies.get("user_role", "customer")`.
   - Injected into template context: `context["current_role"] = role`.

### B. Dynamic Navigation Bar (`frontend/templates/base.html`)
1. **Add Role Context Switcher to the Header**:
   - A modern dropdown pill placed on the right side of the navbar:
     ```html
     <div class="role-selector-container">
       <label for="role-select" class="role-label">Active Role:</label>
       <select id="role-select" class="role-select" onchange="switchRole(this.value)">
         <option value="customer" {% if current_role == 'customer' %}selected{% endif %}>👤 Customer</option>
         <option value="analyst" {% if current_role == 'analyst' %}selected{% endif %}>🛡️ Fraud Analyst</option>
         <option value="admin" {% if current_role == 'admin' %}selected{% endif %}>⚡ System Admin</option>
       </select>
     </div>
     ```
2. **Conditional Navigation Rendering**:
   - `Dashboard`, `Transfer`, `Ledger`: Visible to all roles.
   - `Fraud Alerts`: Wrapped in `{% if current_role in ['analyst', 'admin'] %}`.
   - `Audit Chain`, `Benchmarks`: Wrapped in `{% if current_role == 'admin' %}`.

### C. Dashboard Information Leakage Fix (`frontend/templates/index.html`)
1. **Top KPI Stats Grid**:
   - For `current_role == 'customer'`:
     - **Replace** the `"Open Fraud Alerts"` card with a customer-relevant card: `"KYC Status: VERIFIED"`.
     - **Replace** `"Outbox Queue Depth"` with `"Protected by ACID Ledger"`.
   - For `current_role in ['analyst', 'admin']`:
     - Display `"Open Fraud Alerts"` and `"Outbox Queue Depth"` as intended for operations.
2. **Live Ticker & Quick Transfer**:
   - Mask internal statuses: In customer view, map `APPROVED_UNDER_REVIEW` to `UNDER REVIEW` without mentioning fraud risk scores or isolation forest anomalies.

### D. Route-Level RBAC Gating (`backend/app/main.py`)
Add server-side role validation on UI routes:
1. `/ui/alerts`: Check if `role in ['analyst', 'admin']`. If not, render a polite `403 Forbidden` view or redirect to `/` with an explanatory toast.
2. `/ui/audit`: Check if `role == 'admin'`. If not, return 403 Forbidden.
3. `/ui/benchmarks`: Check if `role == 'admin'`. If not, return 403 Forbidden.

### E. Frontend API Header Synchronization
Update `fetch()` and `htmx` requests in `frontend/static/css/` and templates:
- Read `document.cookie` for `user_role` (or `localStorage`) and automatically attach:
  ```javascript
  headers: {
    'Content-Type': 'application/json',
    'X-User-Role': getActiveRole()
  }
  ```
- This satisfies the backend dependency `@router.post("...", dependencies=[Depends(require_analyst_or_admin)])` in `backend/app/api/security.py`.

---

## 4. Step-by-Step Execution Plan

1. **Backend Route Updates** ([`backend/app/main.py`](file:///c:/Users/Rahul%20A%20S/DBMS/backend/app/main.py)):
   - Implement role extraction helper:
     ```python
     def get_ui_role(request: Request) -> str:
         return request.cookies.get("user_role", "customer").lower()
     ```
   - Protect `/ui/alerts`, `/ui/audit`, and `/ui/benchmarks` using `get_ui_role()`.
   - Add endpoint `POST /api/v1/auth/role` to set/switch roles.
2. **Navbar & Base Template** ([`frontend/templates/base.html`](file:///c:/Users/Rahul%20A%20S/DBMS/frontend/templates/base.html)):
   - Add the role dropdown selector.
   - Conditionally render navigation items based on `current_role`.
   - Add global JavaScript helper `switchRole(role)` that sets the cookie and reloads the page.
3. **Dashboard Gating** ([`frontend/templates/index.html`](file:///c:/Users/Rahul%20A%20S/DBMS/frontend/templates/index.html)):
   - Conditionally render KPI cards (`customer` vs `analyst`/`admin`).
   - Remove internal ML risk score output from customer quick transfer responses.
4. **Style Polish** ([`frontend/static/css/style.css`](file:///c:/Users/Rahul%20A%20S/DBMS/frontend/static/css/style.css)):
   - Add styling for the role selector pill in the header.
5. **Verification & Testing**:
   - Test default view as `customer` &rarr; verify alerts and audit tabs are hidden, and accessing `/ui/alerts` directly is blocked.
   - Switch to `analyst` &rarr; verify Fraud Alerts tab appears and allows review actions.
   - Switch to `admin` &rarr; verify Audit Chain and Benchmarks tabs unlock.

---

## 5. Viva / Demonstration Value
During project presentation, this enables an exact demonstration matching the script:
1. Start in **Customer Role**: *"The customer sees only standard banking operations. Notice there are no fraud indicators or risk numbers displayed."*
2. Execute a suspicious transaction (e.g. ₹75,000): *"The customer simply sees 'Transaction is under review' or 'Declined'."*
3. Switch dropdown to **Fraud Analyst**: *"Now, logging into the Analyst portal, the alert immediately surfaces in the queue with the Isolation Forest score (88/100) and MongoDB rule hits."*

