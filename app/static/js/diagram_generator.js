const markdownInput = document.getElementById("diagram-json-input");
const parseBtn = document.getElementById("diagram-parse-btn");
const generateBtn = document.getElementById("diagram-generate-btn");
const statusNode = document.getElementById("diagram-status");
const groupEditor = document.getElementById("row-group-editor");
const addRowGroupBtn = document.getElementById("add-row-group-btn");
const processResultBox = document.getElementById("process-result-box");
const mermaidPanel = document.getElementById("diagram-mermaid-panel");
const mermaidCode = document.getElementById("diagram-mermaid-code");
const svgPanel = document.getElementById("diagram-svg-panel");
const errorModal = document.getElementById("error-modal");
const errorModalMessage = document.getElementById("error-modal-message");
const errorModalClose = document.getElementById("error-modal-close");

const defaultMarkdown = `# 数据安全治理

## 制度体系
- 制度编制
- 修订机制

## 技术防护
- 加密与脱敏
- 访问控制`;

let currentTopLevelTitles = [];
const topLevelRowGroupMap = {};
const rowGroupKeys = ["group-1", "group-2", "group-3", "group-4"];

const setStatus = (text, isError = false) => {
  statusNode.textContent = text;
  statusNode.classList.toggle("error-text", isError);
};

const renderMermaid = async (code) => {
  if (!window.__diagramMermaid) {
    mermaidPanel.textContent = "Mermaid 加载失败。";
    return;
  }
  window.__diagramMermaid.initialize({ startOnLoad: false, securityLevel: "loose" });
  const renderId = `mermaid-${Date.now()}`;
  const rendered = await window.__diagramMermaid.render(renderId, code);
  mermaidPanel.innerHTML = rendered.svg;
};

const setUiLocked = (locked) => {
  document.body.classList.toggle("ui-locked", locked);
  const nodes = [markdownInput, parseBtn, generateBtn, addRowGroupBtn, ...document.querySelectorAll("#row-group-editor select")];
  nodes.forEach((node) => {
    if (node) {
      node.disabled = locked;
    }
  });
};

const showErrorModal = (message) => {
  errorModalMessage.textContent = message;
  errorModal.classList.remove("hidden");
  if (errorModalClose) {
    errorModalClose.disabled = false;
  }
  setUiLocked(true);
};

const hideErrorModal = () => {
  errorModal.classList.add("hidden");
  setUiLocked(false);
};

window.__closeDiagramErrorModal = hideErrorModal;

const parseMarkdownOutline = (raw) => {
  const lines = (raw || "").replace(/\r\n/g, "\n").split("\n").map((line) => line.trim());
  const nonEmpty = lines.filter((line) => line);
  if (!nonEmpty.length) {
    throw new Error("请输入 Markdown 文本。");
  }

  const rootHeading = nonEmpty.find((line) => /^#\s+/.test(line));
  const rootTitle = rootHeading ? rootHeading.replace(/^#\s+/, "").trim() : nonEmpty[0];
  const children = [];
  let currentTop = null;

  for (const line of lines) {
    if (!line) {
      continue;
    }
    if (/^#\s+/.test(line)) {
      continue;
    }
    if (/^##\s+/.test(line)) {
      const title = line.replace(/^##\s+/, "").trim();
      if (!title) {
        continue;
      }
      currentTop = { title, children: [] };
      children.push(currentTop);
      continue;
    }
    if (!currentTop) {
      continue;
    }
    if (/^###\s+/.test(line)) {
      const subTitle = line.replace(/^###\s+/, "").trim();
      if (subTitle) {
        currentTop.children.push({ title: subTitle });
      }
      continue;
    }
    const bulletMatch = line.match(/^[-*+]\s+(.+)/);
    if (bulletMatch && bulletMatch[1]?.trim()) {
      currentTop.children.push({ title: bulletMatch[1].trim() });
      continue;
    }
    const numberedMatch = line.match(/^\d+[.)]\s+(.+)/);
    if (numberedMatch && numberedMatch[1]?.trim()) {
      currentTop.children.push({ title: numberedMatch[1].trim() });
      continue;
    }
    currentTop.children.push({ title: line });
  }

  if (!children.length) {
    throw new Error("Markdown 中至少需要一个一级标题（## 标题）。");
  }
  return { title: rootTitle, children };
};

const renderRowGroupEditor = (titles) => {
  currentTopLevelTitles = titles.slice();
  if (!titles.length) {
    groupEditor.textContent = "未检测到一级标题。";
    groupEditor.classList.add("muted");
    return;
  }

  groupEditor.classList.remove("muted");
  const rows = titles
    .map((title) => {
      const selected = topLevelRowGroupMap[title] || "none";
      const dynamicOptions = rowGroupKeys
        .map((groupKey, index) => `<option value="${groupKey}" ${selected === groupKey ? "selected" : ""}>同排组 ${index + 1}</option>`)
        .join("");
      return `
        <div class="group-editor-row">
          <div class="group-editor-title">${title}</div>
          <select data-title="${title.replace(/"/g, "&quot;")}">
            <option value="none" ${selected === "none" ? "selected" : ""}>单独一行</option>
            ${dynamicOptions}
          </select>
        </div>`;
    })
    .join("");
  groupEditor.innerHTML = rows;

  groupEditor.querySelectorAll("select").forEach((select) => {
    select.addEventListener("change", () => {
      const title = select.getAttribute("data-title");
      if (title) {
        topLevelRowGroupMap[title] = select.value;
      }
    });
  });
};

const parseAndSyncRowGroups = () => {
  const outline = parseMarkdownOutline(markdownInput.value.trim());
  const titles = outline.children.map((item) => item.title).filter(Boolean);
  renderRowGroupEditor(titles);
  return outline;
};

const buildOutlineForApi = (outline) => {
  return {
    title: outline.title,
    children: outline.children.map((node) => {
      const rowGroup = topLevelRowGroupMap[node.title];
      return {
        title: node.title,
        row_group: rowGroup && rowGroup !== "none" ? rowGroup : undefined,
        children: (node.children || []).map((leaf) => ({ title: leaf.title }))
      };
    })
  };
};

const validateRowGroups = (outline) => {
  const byGroup = new Map();
  for (const node of outline.children) {
    const group = topLevelRowGroupMap[node.title];
    if (!group || group === "none") {
      continue;
    }
    if (!byGroup.has(group)) {
      byGroup.set(group, []);
    }
    byGroup.get(group).push(node.title);
  }

  const failedTitles = new Set();
  const messages = [];
  for (const [group, titles] of byGroup.entries()) {
    if (titles.length > 3) {
      titles.forEach((title) => failedTitles.add(title));
      messages.push(`${group} 选择了 ${titles.length} 个一级标题（最多 3 个）`);
    }
  }
  return { failedTitles, messages };
};

const fillProcessResult = (outline, failedTitles) => {
  const lines = outline.children.map((node) => {
    const failed = failedTitles.has(node.title);
    return `${node.title} ${failed ? "❌" : "✅"}`;
  });
  processResultBox.value = lines.join("\n") || "暂无处理结果。";
};

const generate = async () => {
  let outline;
  try {
    outline = parseAndSyncRowGroups();
  } catch (error) {
    setStatus(error.message || "Markdown 解析失败。", true);
    showErrorModal(error.message || "Markdown 解析失败。");
    return;
  }

  const validation = validateRowGroups(outline);
  fillProcessResult(outline, validation.failedTitles);
  if (validation.messages.length) {
    const msg = `同排分组不合法：${validation.messages.join("；")}。请点击右上角 × 关闭后修改。`;
    setStatus(msg, true);
    showErrorModal(msg);
    return;
  }

  generateBtn.disabled = true;
  setStatus("正在生成图表...");

  try {
    const outlineForApi = buildOutlineForApi(outline);
    const resp = await fetch("/api/diagram/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ diagram_outline_text: JSON.stringify(outlineForApi) })
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || "生成失败");
    }

    mermaidCode.value = data.diagram_mermaid || "";
    svgPanel.innerHTML = data.diagram_layered_svg || "";
    await renderMermaid(data.diagram_mermaid || "graph TD");
    setStatus("生成成功。");
  } catch (error) {
    const msg = error.message || "生成失败，请检查 Markdown 或分组设置。";
    setStatus(msg, true);
    showErrorModal(msg);
  } finally {
    generateBtn.disabled = false;
  }
};

if (markdownInput) {
  markdownInput.value = defaultMarkdown;
}

if (parseBtn) {
  parseBtn.addEventListener("click", () => {
    try {
      parseAndSyncRowGroups();
      setStatus("一级标题解析成功，可继续设置同排分组。");
    } catch (error) {
      const msg = error.message || "解析失败。";
      setStatus(msg, true);
      showErrorModal(msg);
    }
  });
}

if (generateBtn) {
  generateBtn.addEventListener("click", generate);
}

if (addRowGroupBtn) {
  addRowGroupBtn.addEventListener("click", () => {
    const nextIndex = rowGroupKeys.length + 1;
    rowGroupKeys.push(`group-${nextIndex}`);
    renderRowGroupEditor(currentTopLevelTitles);
    setStatus(`已新增同排组 ${nextIndex}。`);
  });
}

if (errorModalClose) {
  errorModalClose.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    hideErrorModal();
  });
}

if (errorModal) {
  errorModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.id === "error-modal-close") {
      event.preventDefault();
      event.stopPropagation();
      hideErrorModal();
    }
  }, true);
}

try {
  parseAndSyncRowGroups();
} catch (error) {
  setStatus(error.message || "初始化解析失败。", true);
}
