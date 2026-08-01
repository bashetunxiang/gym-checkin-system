async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => ({ ok: false, message: "响应解析失败。" }));
  if (!response.ok || data.ok === false) {
    throw new Error(data.message || "请求失败。");
  }
  return data.data ?? data;
}

function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2400);
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

function emptyRow(colspan, text = "暂无数据") {
  return `<tr><td colspan="${colspan}">${text}</td></tr>`;
}

function recordCells(record, includeStatus = false) {
  const cells = [
    `<td>第${record.sequence}个</td>`,
    `<td>${record.person_id}</td>`,
    `<td>${record.person_name}</td>`,
    `<td>${record.enter_time}</td>`,
    `<td>${record.leave_time || "未离馆"}</td>`,
    `<td>${record.duration_text}</td>`,
  ];
  if (includeStatus) {
    const statusClass = record.status === "在馆" ? "is-inside" : "is-left";
    cells.push(`<td><span class="status-badge ${statusClass}">${record.status}</span></td>`);
  }
  return cells.join("");
}

function initLoginPage() {
  const form = document.getElementById("loginForm");
  const message = document.getElementById("loginMessage");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.textContent = "";
    const formData = new FormData(form);
    try {
      const result = await apiRequest("/api/login", {
        method: "POST",
        body: JSON.stringify({
          username: formData.get("username"),
          password: formData.get("password"),
        }),
      });
      window.location.href = result.redirect || "/dashboard";
    } catch (error) {
      message.textContent = error.message;
    }
  });
}

function initRegisterPage() {
  const form = document.getElementById("registerForm");
  const message = document.getElementById("registerMessage");
  const card = document.getElementById("initialPasswordCard");
  const passwordNode = document.getElementById("initialPassword");
  const copyButton = document.getElementById("copyInitialPassword");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.textContent = "";
    message.classList.remove("success");
    card.hidden = true;
    const formData = new FormData(form);
    try {
      const result = await apiRequest("/api/register", {
        method: "POST",
        body: JSON.stringify({ username: formData.get("username") }),
      });
      passwordNode.textContent = result.initial_password;
      card.hidden = false;
      message.textContent = result.message;
      message.classList.add("success");
      form.querySelector("button").disabled = true;
    } catch (error) {
      message.textContent = error.message;
    }
  });

  if (copyButton) {
    copyButton.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(passwordNode.textContent);
        copyButton.textContent = "已复制";
      } catch (_error) {
        copyButton.textContent = "请手动复制";
      }
    });
  }
}

function initForgotPasswordPage() {
  const form = document.getElementById("forgotPasswordForm");
  const message = document.getElementById("forgotPasswordMessage");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.textContent = "";
    message.classList.remove("success");
    const formData = new FormData(form);
    try {
      const result = await apiRequest("/api/password/forgot", {
        method: "POST",
        body: JSON.stringify({
          username: formData.get("username"),
          initial_password: formData.get("initial_password"),
          new_password: formData.get("new_password"),
          confirm_password: formData.get("confirm_password"),
        }),
      });
      message.textContent = result.message;
      message.classList.add("success");
      form.reset();
      window.setTimeout(() => {
        window.location.href = result.redirect || "/login";
      }, 1200);
    } catch (error) {
      message.textContent = error.message;
    }
  });
}

async function loadSummary() {
  const summary = await apiRequest("/api/summary");
  setText("todayEnterCount", summary.today_enter_count);
  setText("insideCount", summary.current_inside_count);
  setText("todayLeaveCount", summary.today_leave_count);
  setText("averageStayText", summary.average_stay_text);
}

async function renderDashboardInside() {
  const rows = document.getElementById("dashboardInsideRows");
  if (!rows) return;
  const records = await apiRequest("/api/inside");
  rows.innerHTML = records.length
    ? records.slice(0, 6).map((record) => `
      <tr>
        <td>第${record.sequence}个</td>
        <td>${record.person_id}</td>
        <td>${record.person_name}</td>
        <td>${record.enter_time}</td>
      </tr>
    `).join("")
    : emptyRow(4, "当前没有在馆人员");
}

function renderChart(id, option) {
  const node = document.getElementById(id);
  if (!node) return;
  if (!window.echarts) {
    node.innerHTML = '<div class="result-box">ECharts 未加载，请检查网络或静态资源。</div>';
    return;
  }
  const chart = echarts.init(node);
  chart.setOption(option);
  window.addEventListener("resize", () => chart.resize());
}

let echartsLoadingPromise = null;

function ensureEcharts() {
  if (window.echarts) return Promise.resolve(true);
  if (echartsLoadingPromise) return echartsLoadingPromise;
  echartsLoadingPromise = new Promise((resolve) => {
    const script = document.createElement("script");
    const timer = window.setTimeout(() => resolve(false), 3000);
    script.src = "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js";
    script.onload = () => {
      window.clearTimeout(timer);
      resolve(Boolean(window.echarts));
    };
    script.onerror = () => {
      window.clearTimeout(timer);
      resolve(false);
    };
    document.head.appendChild(script);
  });
  return echartsLoadingPromise;
}

async function renderDailyChart(id = "dailyChart") {
  await ensureEcharts();
  const analytics = await apiRequest("/api/analytics");
  const daily = analytics.daily;
  const dailyGradient = window.echarts
    ? new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: "#53c7ff" },
      { offset: 0.55, color: "#478cff" },
      { offset: 1, color: "#735cff" },
    ])
    : "#35b9ff";
  renderChart(id, {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(7, 20, 40, 0.94)",
      borderColor: "rgba(83, 199, 255, 0.35)",
      textStyle: { color: "#eaf5ff" },
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(83,199,255,0.06)" } },
    },
    grid: { left: 42, right: 18, top: 30, bottom: 34 },
    xAxis: {
      type: "category",
      data: daily.map((item) => item.date),
      axisLabel: { color: "#8fb0d4" },
      axisLine: { lineStyle: { color: "#1d4670" } },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#8fb0d4" },
      splitLine: { lineStyle: { color: "rgba(141,178,212,0.16)" } },
    },
    series: [
      {
        name: "到馆次数",
        type: "bar",
        data: daily.map((item) => item.records_count),
        itemStyle: {
          color: dailyGradient,
          borderRadius: [7, 7, 2, 2],
          shadowBlur: 14,
          shadowColor: "rgba(61, 151, 255, 0.28)",
        },
        barMaxWidth: 28,
      },
    ],
  });
  return analytics;
}

async function initDashboardPage() {
  await Promise.all([loadSummary(), renderDashboardInside(), renderDailyChart()]);
}

function initVideoPage() {
  const form = document.getElementById("checkinForm");
  const result = document.getElementById("checkinResult");
  initCameraPreview();
  initFaceEnrollControls();
  initAutoCheckinControls();
  if (!form) return;
  form.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const formData = new FormData(form);
      const action = button.dataset.action;
      const url = action === "enter" ? "/api/checkin/enter" : "/api/checkin/leave";
      try {
        const record = await apiRequest(url, {
          method: "POST",
          body: JSON.stringify({
            person_id: formData.get("person_id"),
            person_name: formData.get("person_name"),
          }),
        });
        result.innerHTML = `
          <strong>${action === "enter" ? "进入场馆成功" : "离开场馆成功"}</strong><br>
          第${record.sequence}个进入场馆，人员编号 ${record.person_id}，姓名 ${record.person_name}<br>
          进入时间：${record.enter_time}，离馆时间：${record.leave_time || "未离馆"}，停留时间：${record.duration_text}
        `;
        showToast("打卡记录已更新");
      } catch (error) {
        result.textContent = error.message;
      }
    });
  });
}

async function initCameraPreview() {
  const frame = document.querySelector(".camera-frame");
  const img = document.getElementById("cameraStream");
  const status = document.getElementById("cameraStatus");
  const statusBar = document.getElementById("cameraStatusBar");
  if (!frame || !img || !status) return;
  try {
    const camera = await apiRequest("/api/camera/status");
    status.textContent = camera.message;
    if (statusBar) statusBar.textContent = camera.message;
    img.src = `/video_feed?t=${Date.now()}`;
    frame.classList.add("camera-on");
    const refreshStatus = async () => {
      try {
        const cameraStatus = await apiRequest(`/api/camera/status?t=${Date.now()}`);
        status.textContent = cameraStatus.message;
        if (statusBar) statusBar.textContent = cameraStatus.message;
      } catch (error) {
        status.textContent = error.message;
        if (statusBar) statusBar.textContent = error.message;
      }
    };
    window.setInterval(refreshStatus, 1500);
  } catch (error) {
    status.textContent = error.message;
    if (statusBar) statusBar.textContent = error.message;
  }
}

function initFaceEnrollControls() {
  const form = document.getElementById("faceEnrollForm");
  const trainButton = document.getElementById("trainFaceModel");
  const result = document.getElementById("faceEnrollResult");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(form);
      try {
        const data = await apiRequest("/api/face/enroll", {
          method: "POST",
          body: JSON.stringify({ person_id: formData.get("person_id") }),
        });
        result.innerHTML = `
          <strong>采集成功</strong><br>
          人员编号：${data.person_id}<br>
          当前样本数：${data.sample_count}
        `;
        showToast("人脸样本已保存");
      } catch (error) {
        result.textContent = error.message;
      }
    });
  }
  if (trainButton) {
    trainButton.addEventListener("click", async () => {
      try {
        trainButton.disabled = true;
        trainButton.textContent = "训练中...";
        const data = await apiRequest("/api/face/train", { method: "POST", body: "{}" });
        result.innerHTML = `
          <strong>训练完成</strong><br>
          已训练人员数：${data.person_count}<br>
          样本总数：${data.sample_count}
        `;
        showToast("人脸识别模型已更新");
      } catch (error) {
        result.textContent = error.message;
      } finally {
        trainButton.disabled = false;
        trainButton.textContent = "训练识别模型";
      }
    });
  }
}

let autoCheckinTimer = null;

function initAutoCheckinControls() {
  const mode = document.getElementById("autoCheckinMode");
  const onceButton = document.getElementById("autoCheckinOnce");
  const toggleButton = document.getElementById("autoCheckinToggle");
  const result = document.getElementById("autoCheckinResult");
  if (!mode || !onceButton || !toggleButton || !result) return;

  const runAutoCheckin = async () => {
    try {
      const data = await apiRequest("/api/face/auto_checkin", {
        method: "POST",
        body: JSON.stringify({ mode: mode.value }),
      });
      const record = data.record;
      result.innerHTML = `
        <strong>${data.message}</strong><br>
        ${record ? `第${record.sequence}个进入场馆，人员编号：${record.person_id}<br>
        进入时间：${record.enter_time}，离馆时间：${record.leave_time || "未离馆"}，停留时间：${record.duration_text}` : ""}
      `;
      if (!data.skipped) showToast(data.message);
    } catch (error) {
      result.textContent = error.message;
    }
  };

  onceButton.addEventListener("click", runAutoCheckin);
  toggleButton.addEventListener("click", () => {
    if (autoCheckinTimer) {
      window.clearInterval(autoCheckinTimer);
      autoCheckinTimer = null;
      toggleButton.textContent = "开启自动打卡";
      result.textContent = "自动打卡已停止。";
      return;
    }
    runAutoCheckin();
    autoCheckinTimer = window.setInterval(runAutoCheckin, 2500);
    toggleButton.textContent = "停止自动打卡";
    result.textContent = "自动打卡运行中...";
  });
}

async function loadPersons() {
  const rows = document.getElementById("personRows");
  if (!rows) return;
  const persons = await apiRequest("/api/persons");
  rows.innerHTML = persons.length
    ? persons.map((person) => `
      <tr>
        <td>${person.person_id}</td>
        <td>${person.name}</td>
        <td>${person.phone || ""}</td>
        <td>${person.remark || ""}</td>
      </tr>
    `).join("")
    : emptyRow(4, "暂无人员信息");
}

function initPersonsPage() {
  const form = document.getElementById("personForm");
  const refresh = document.getElementById("refreshPersons");
  if (refresh) refresh.addEventListener("click", loadPersons);
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(form);
      try {
        await apiRequest("/api/persons", {
          method: "POST",
          body: JSON.stringify({
            person_id: formData.get("person_id"),
            name: formData.get("name"),
            phone: formData.get("phone"),
            remark: formData.get("remark"),
          }),
        });
        form.reset();
        showToast("人员信息已保存");
        await loadPersons();
      } catch (error) {
        showToast(error.message);
      }
    });
  }
  loadPersons();
}

async function loadInside() {
  const rows = document.getElementById("insideRows");
  if (!rows) return;
  const records = await apiRequest("/api/inside");
  rows.innerHTML = records.length
    ? records.map((record) => `<tr>${recordCells(record)}</tr>`).join("")
    : emptyRow(6, "当前没有在馆人员");
}

function initInsidePage() {
  const refresh = document.getElementById("refreshInside");
  if (refresh) refresh.addEventListener("click", loadInside);
  loadInside();
}

async function loadRecords() {
  const rows = document.getElementById("recordRows");
  if (!rows) return;
  const records = await apiRequest("/api/records");
  rows.innerHTML = records.length
    ? records.map((record) => `<tr>${recordCells(record, true)}</tr>`).join("")
    : emptyRow(7, "暂无到馆记录");
}

function initRecordsPage() {
  const refresh = document.getElementById("refreshRecords");
  if (refresh) refresh.addEventListener("click", loadRecords);
  loadRecords();
}

async function initAnalyticsPage() {
  const analytics = await renderDailyChart("analyticsDailyChart");
  const rows = analytics.monthly_rows;
  setText("monthlyTotal", `累计 ${analytics.monthly_total_text}`);
  const monthlyGradient = window.echarts
    ? new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: "#52f0c2" },
      { offset: 0.55, color: "#28c7bd" },
      { offset: 1, color: "#438cff" },
    ])
    : "#33dfb0";
  renderChart("analyticsMonthlyChart", {
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(7, 20, 40, 0.94)",
      borderColor: "rgba(51, 223, 176, 0.35)",
      textStyle: { color: "#eaf5ff" },
    },
    grid: { left: 52, right: 18, top: 30, bottom: 34 },
    xAxis: {
      type: "category",
      data: rows.map((item) => item.person_name || item.person_id),
      axisLabel: { color: "#8fb0d4" },
      axisLine: { lineStyle: { color: "#1d4670" } },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#8fb0d4" },
      splitLine: { lineStyle: { color: "rgba(141,178,212,0.16)" } },
    },
    series: [{
      name: "在馆分钟",
      type: "bar",
      data: rows.map((item) => Math.round(Number(item.stay_seconds || 0) / 60)),
      itemStyle: {
        color: monthlyGradient,
        borderRadius: [7, 7, 2, 2],
        shadowBlur: 14,
        shadowColor: "rgba(51, 223, 176, 0.24)",
      },
      barMaxWidth: 30,
    }],
  });
  const tableRows = document.getElementById("monthlyRows");
  if (tableRows) {
    tableRows.innerHTML = rows.length
      ? rows.map((row) => `
        <tr>
          <td>${row.person_id}</td>
          <td>${row.person_name}</td>
          <td>${row.visit_count}</td>
          <td>${row.stay_text}</td>
        </tr>
      `).join("")
      : emptyRow(4, "本月暂无到馆记录");
  }
}

async function loadSettings() {
  const settings = await apiRequest("/api/settings");
  setText("settingUsername", settings.username || "-");
  setText("settingPersonCount", settings.person_count);
  setText("settingRecordCount", settings.record_count);
  const rows = document.getElementById("settingsRows");
  if (!rows) return;
  rows.innerHTML = settings.files.map((file) => `
    <tr>
      <td>${file.label}</td>
      <td>${file.path}</td>
      <td>${file.exists ? "是" : "否"}</td>
      <td>${file.size} 字节</td>
    </tr>
  `).join("");
}

function initSettingsPage() {
  const refresh = document.getElementById("refreshSettings");
  if (refresh) refresh.addEventListener("click", loadSettings);
  initChangePasswordForm();
  loadSettings();
}

function initChangePasswordForm() {
  const form = document.getElementById("changePasswordForm");
  const message = document.getElementById("changePasswordMessage");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.textContent = "";
    message.classList.remove("success");
    const formData = new FormData(form);
    try {
      const result = await apiRequest("/api/password/change", {
        method: "POST",
        body: JSON.stringify({
          current_password: formData.get("current_password"),
          new_password: formData.get("new_password"),
          confirm_password: formData.get("confirm_password"),
        }),
      });
      message.textContent = result.message;
      message.classList.add("success");
      form.reset();
      const notice = document.querySelector(".notice-banner");
      if (notice) notice.remove();
    } catch (error) {
      message.textContent = error.message;
    }
  });
}

function initTimeSky() {
  const sky = document.getElementById("timeSky");
  const timeNode = document.getElementById("skyTime");
  const dateNode = document.getElementById("skyDate");
  const periodNode = document.getElementById("skyPeriod");
  if (!sky || !timeNode || !dateNode || !periodNode || sky.dataset.ready) return;
  sky.dataset.ready = "true";

  const update = () => {
    const now = new Date();
    const hour = now.getHours();
    const preciseHour = hour + now.getMinutes() / 60 + now.getSeconds() / 3600;
    const isDay = preciseHour >= 6 && preciseHour < 18;
    const progress = isDay
      ? (preciseHour - 6) / 12
      : ((preciseHour >= 18 ? preciseHour - 18 : preciseHour + 6) / 12);
    const x = 4 + progress * 92;
    const y = 76 - Math.sin(Math.PI * progress) * 58;

    sky.style.setProperty("--orb-x", `${x}%`);
    sky.style.setProperty("--orb-y", `${y}%`);
    sky.classList.toggle("day", isDay);
    sky.classList.toggle("night", !isDay);
    sky.classList.toggle("dawn", preciseHour >= 5 && preciseHour < 8);
    sky.classList.toggle("dusk", preciseHour >= 17 && preciseHour < 20);

    timeNode.textContent = new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(now);
    dateNode.textContent = new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      weekday: "long",
    }).format(now);
    if (hour >= 5 && hour < 8) periodNode.textContent = "清晨 · 太阳升起";
    else if (hour >= 8 && hour < 12) periodNode.textContent = "上午 · 日光渐盛";
    else if (hour >= 12 && hour < 17) periodNode.textContent = "下午 · 太阳西行";
    else if (hour >= 17 && hour < 20) periodNode.textContent = "傍晚 · 日落时分";
    else periodNode.textContent = "夜间 · 月亮巡行";
  };

  update();
  window.setInterval(update, 1000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initTimeSky);
} else {
  initTimeSky();
}
