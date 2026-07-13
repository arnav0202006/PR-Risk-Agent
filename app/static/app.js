(function () {
  "use strict";

  const MAX_DIFF_CHARS = 50000;

  const form = document.getElementById("analyze-form");
  const diffField = document.getElementById("diff");
  const diffCount = document.getElementById("diff-count");
  const formError = document.getElementById("form-error");
  const analyzeBtn = document.getElementById("analyze-btn");
  const sampleBtn = document.getElementById("sample-btn");
  const results = document.getElementById("results");

  const SAMPLE = {
    pr_title: "Add bulk user cleanup endpoint for admin dashboard",
    pr_description:
      "Adds a new endpoint so admins can search for users by name and delete inactive " +
      "accounts in bulk from the dashboard. Reuses the existing db connection helper.",
    context:
      "Public FastAPI service backed by PostgreSQL. Deployed several times a day via CI/CD. " +
      "No staging environment; deploys go straight to production.",
    diff: `diff --git a/app/routes/admin.py b/app/routes/admin.py
index 3f2a1c9..8b6e2aa 100644
--- a/app/routes/admin.py
+++ b/app/routes/admin.py
@@ -10,25 +10,40 @@ from app.db import get_connection
 router = APIRouter()

-@router.get("/admin/users/search")
-def search_users(name: str, current_user: User = Depends(require_admin)):
-    conn = get_connection()
-    cursor = conn.cursor()
-    cursor.execute("SELECT id, name, email, active FROM users WHERE name = %s", (name,))
-    return cursor.fetchall()
+@router.get("/admin/users/search")
+def search_users(name: str):
+    conn = get_connection()
+    cursor = conn.cursor()
+    query = "SELECT id, name, email, active FROM users WHERE name = '" + name + "'"
+    try:
+        cursor.execute(query)
+        return cursor.fetchall()
+    except Exception:
+        pass
+
+
+@router.post("/admin/users/cleanup")
+def cleanup_inactive_users(days_inactive: int = 90):
+    conn = get_connection()
+    cursor = conn.cursor()
+    cursor.execute(
+        "DELETE FROM users WHERE last_login < NOW() - INTERVAL '%s days'" % days_inactive
+    )
+    conn.commit()
+    return {"status": "ok"}
`,
  };

  function setCharCount() {
    const len = diffField.value.length;
    diffCount.textContent = `${len.toLocaleString()} / ${MAX_DIFF_CHARS.toLocaleString()}`;
    diffCount.classList.remove("limit-near", "limit-exceeded");
    if (len > MAX_DIFF_CHARS) {
      diffCount.classList.add("limit-exceeded");
    } else if (len > MAX_DIFF_CHARS * 0.9) {
      diffCount.classList.add("limit-near");
    }
  }

  function showFormError(message) {
    formError.textContent = message;
    formError.hidden = false;
  }

  function clearFormError() {
    formError.textContent = "";
    formError.hidden = true;
  }

  function setLoading(isLoading) {
    analyzeBtn.disabled = isLoading;
    analyzeBtn.querySelector(".spinner").hidden = !isLoading;
    analyzeBtn.querySelector(".btn-label").textContent = isLoading
      ? "Analyzing..."
      : "Analyze PR";
  }

  function el(tag, opts) {
    const node = document.createElement(tag);
    opts = opts || {};
    if (opts.className) node.className = opts.className;
    if (opts.text !== undefined) node.textContent = opts.text;
    return node;
  }

  function fillList(listEl, emptyEl, items) {
    listEl.replaceChildren();
    if (!items || items.length === 0) {
      emptyEl.hidden = false;
      return;
    }
    emptyEl.hidden = true;
    items.forEach((item) => {
      const li = el("li", { text: item });
      listEl.appendChild(li);
    });
  }

  function formatLabel(value) {
    if (!value) return "";
    return value
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");
  }

  function renderFindings(findings) {
    const list = document.getElementById("findings-list");
    const empty = document.getElementById("findings-empty");
    list.replaceChildren();

    if (!findings || findings.length === 0) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;

    const severityOrder = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
    const sorted = [...findings].sort(
      (a, b) => (severityOrder[a.severity] ?? 5) - (severityOrder[b.severity] ?? 5)
    );

    sorted.forEach((finding) => {
      const card = el("div", {
        className: `finding-card severity-${finding.severity || "info"}`,
      });

      const header = el("div", { className: "finding-header" });
      header.appendChild(el("span", { className: "finding-title", text: finding.title || "Untitled finding" }));

      const severityBadge = el("span", {
        className: `badge badge-${finding.severity || "info"}`,
        text: finding.severity || "info",
      });
      header.appendChild(severityBadge);
      header.appendChild(
        el("span", { className: "finding-category", text: formatLabel(finding.category) })
      );
      card.appendChild(header);

      if (finding.explanation) {
        card.appendChild(el("p", { className: "finding-explanation", text: finding.explanation }));
      }

      if (finding.evidence) {
        const meta = el("p", { className: "finding-meta" });
        meta.appendChild(el("strong", { text: "Evidence" }));
        card.appendChild(meta);
        card.appendChild(el("code", { className: "finding-evidence", text: finding.evidence }));
      }

      if (finding.suggested_fix) {
        const fix = el("p", { className: "finding-meta" });
        fix.appendChild(el("strong", { text: "Suggested fix: " }));
        fix.appendChild(document.createTextNode(finding.suggested_fix));
        card.appendChild(fix);
      }

      list.appendChild(card);
    });
  }

  function renderMissingTests(missingTests) {
    const list = document.getElementById("missing-tests-list");
    const empty = document.getElementById("missing-tests-empty");
    list.replaceChildren();

    if (!missingTests || missingTests.length === 0) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;

    missingTests.forEach((item) => {
      const li = el("li");
      const strong = el("strong", { text: item.test || "Untitled test" });
      li.appendChild(strong);
      if (item.priority) {
        li.appendChild(document.createTextNode(` — priority: ${item.priority}`));
      }
      if (item.reason) {
        li.appendChild(document.createElement("br"));
        li.appendChild(document.createTextNode(item.reason));
      }
      list.appendChild(li);
    });
  }

  function renderResults(data) {
    document.getElementById("risk-badge").textContent = formatLabel(data.risk_level);
    document.getElementById("risk-badge").className = `badge badge-lg badge-${data.risk_level}`;

    document.getElementById("recommendation-badge").textContent = formatLabel(
      data.merge_recommendation
    );
    document.getElementById("recommendation-badge").className =
      `badge badge-lg badge-${data.merge_recommendation}`;

    const confidence = Math.round(data.confidence_score ?? 0);
    document.getElementById("confidence-fill").style.width = `${confidence}%`;
    document.getElementById("confidence-value").textContent = `${confidence}%`;

    document.getElementById("summary-text").textContent = data.summary || "";
    document.getElementById("final-reasoning-text").textContent = data.final_reasoning || "";

    renderFindings(data.findings);
    renderMissingTests(data.missing_tests);
    fillList(
      document.getElementById("deployment-list"),
      document.getElementById("deployment-empty"),
      data.deployment_considerations
    );
    fillList(
      document.getElementById("rollback-list"),
      document.getElementById("rollback-empty"),
      data.rollback_plan
    );
    fillList(
      document.getElementById("positive-list"),
      document.getElementById("positive-empty"),
      data.positive_observations
    );

    results.hidden = false;
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function handleSubmit(evt) {
    evt.preventDefault();
    clearFormError();

    const diffValue = diffField.value.trim();
    if (!diffValue) {
      showFormError("Please paste a git diff or code change before analyzing.");
      diffField.focus();
      return;
    }
    if (diffValue.length > MAX_DIFF_CHARS) {
      showFormError(`The diff is too long. Please keep it under ${MAX_DIFF_CHARS.toLocaleString()} characters.`);
      return;
    }

    const payload = {
      pr_title: document.getElementById("pr_title").value.trim(),
      pr_description: document.getElementById("pr_description").value.trim(),
      diff: diffValue,
      context: document.getElementById("context").value.trim(),
    };

    setLoading(true);
    results.hidden = true;

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const message =
          (data && (data.error || (data.details && data.details.join(" ")))) ||
          "Something went wrong while analyzing this PR. Please try again.";
        showFormError(message);
        return;
      }

      renderResults(data);
    } catch (err) {
      showFormError("Could not reach the analysis service. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }

  function loadSample() {
    document.getElementById("pr_title").value = SAMPLE.pr_title;
    document.getElementById("pr_description").value = SAMPLE.pr_description;
    document.getElementById("context").value = SAMPLE.context;
    diffField.value = SAMPLE.diff;
    setCharCount();
    clearFormError();
    results.hidden = true;
    diffField.focus();
  }

  diffField.addEventListener("input", setCharCount);
  form.addEventListener("submit", handleSubmit);
  sampleBtn.addEventListener("click", loadSample);

  setCharCount();
})();
