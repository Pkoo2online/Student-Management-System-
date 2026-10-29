let csrfToken = "";
let currentUser = null;
let studentsCache = [];
let classesCache = [];
let classChart = null;

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) =>
  ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[char]);

async function api(url, options = {}) {
  const headers = {...(options.headers || {})};
  if (options.body) headers["Content-Type"] = "application/json";
  if (csrfToken && ["POST", "PUT", "DELETE"].includes(options.method)) {
    headers["X-CSRF-Token"] = csrfToken;
  }
  const response = await fetch(url, {...options, headers});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed.");
  return data;
}

function showNotice(message, isError = false) {
  const notice = $("#notice");
  notice.textContent = message;
  notice.className = `notice show ${isError ? "error" : "success"}`;
  window.setTimeout(() => { notice.className = "notice"; }, 4000);
}

function populateSelect(select, items, label, valueKey = "id") {
  const initial = select.options[0]?.outerHTML || "";
  select.innerHTML = initial + items.map((item) =>
    `<option value="${escapeHtml(item[valueKey])}">${escapeHtml(label(item))}</option>`).join("");
}

async function loadBootstrapData() {
  const [classData, subjectData, studentData] = await Promise.all([
    api("/api/classes"), api("/api/subjects"), api("/api/students?sort=name")
  ]);
  classesCache = classData.classes;
  studentsCache = studentData.students;
  document.querySelectorAll(".class-options").forEach((select) =>
    populateSelect(select, classesCache, (item) => item.name));
  populateSelect($("#class-filter"), classesCache, (item) => item.name);
  document.querySelectorAll(".student-options").forEach((select) =>
    populateSelect(select, studentsCache, (item) => `${item.name} · ${item.enrollment_no}`));
  populateSelect($("#subject-options"), subjectData.subjects,
    (item) => `${item.name} (${item.code})`);
  setDefaultDate();
  renderStudents(studentsCache);
}

function setDefaultDate() {
  document.querySelectorAll('input[name="attendance_date"]').forEach((input) => {
    input.value = new Date().toISOString().slice(0, 10);
    input.max = input.value;
  });
}

function renderStudents(students) {
  const body = $("#students-body");
  if (!students.length) {
    body.innerHTML = '<tr><td colspan="5">No students found.</td></tr>';
    return;
  }
  body.innerHTML = students.map((student) => `<tr>
    <td><div class="student-cell"><span class="avatar">${escapeHtml(student.name.slice(0, 1).toUpperCase())}</span><strong>${escapeHtml(student.name)}</strong></div></td>
    <td>${escapeHtml(student.enrollment_no)}</td><td>${escapeHtml(student.class_name)}</td><td>${escapeHtml(student.email)}</td>
    <td>${currentUser.role === "admin" ? `<button class="table-action" data-edit="${student.id}">Edit</button> <button class="table-action delete" data-delete="${student.id}">Delete</button>` : ""}</td>
  </tr>`).join("");
}

async function refreshStudents() {
  const params = new URLSearchParams();
  if ($("#student-search").value.trim()) params.set("q", $("#student-search").value.trim());
  if ($("#class-filter").value) params.set("class_id", $("#class-filter").value);
  params.set("sort", $("#student-sort").value);
  const result = await api(`/api/students?${params}`);
  renderStudents(result.students);
}

async function loadDashboard() {
  const data = await api("/api/dashboard");
  $("#student-count").textContent = data.student_count;
  $("#present-count").textContent = data.present_today;
  $("#attendance-rate").textContent = `${data.attendance_percentage}%`;
  if (classChart) classChart.destroy();
  if (window.Chart) {
    classChart = new Chart($("#class-chart"), {
      type: "bar",
      data: {
        labels: data.class_counts.map((item) => item.name),
        datasets: [{data: data.class_counts.map((item) => item.total),
          backgroundColor: ["#4668e8", "#7589ed", "#9aa9f3", "#c2cbfa"],
          borderRadius: 7, maxBarThickness: 45}]
      },
      options: {maintainAspectRatio: false, plugins: {legend: {display: false}},
        scales: {y: {beginAtZero: true, ticks: {precision: 0}}, x: {grid: {display: false}}}}
    });
  }
}

async function loadAttendance() {
  const result = await api("/api/attendance");
  $("#attendance-body").innerHTML = result.attendance.map((row) =>
    `<tr><td><strong>${escapeHtml(row.student_name)}</strong></td><td>${escapeHtml(row.attendance_date)}</td>
    <td><span class="badge ${row.status.toLowerCase()}">${escapeHtml(row.status)}</span></td></tr>`).join("")
    || '<tr><td colspan="3">No attendance records.</td></tr>';
}

async function loadMarks() {
  const result = await api("/api/marks");
  $("#marks-body").innerHTML = result.marks.map((row) =>
    `<tr><td><strong>${escapeHtml(row.student_name)}</strong></td><td>${escapeHtml(row.subject_name)}</td>
    <td>${escapeHtml(row.score)} / 100</td><td><span class="badge">${escapeHtml(row.grade)}</span></td></tr>`).join("")
    || '<tr><td colspan="4">No marks available.</td></tr>';
}

function showView(name) {
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === name));
  $(`#${name}-view`).classList.add("active");
  $("#page-title").textContent = {overview: "Dashboard", students: "Students",
    attendance: "Attendance", marks: "Marks & grades"}[name];
  if (name === "attendance") loadAttendance().catch((error) => showNotice(error.message, true));
  if (name === "marks") loadMarks().catch((error) => showNotice(error.message, true));
}

function openStudentDialog(student = null) {
  const dialog = $("#student-dialog");
  const form = $("#student-form");
  form.reset();
  $("#student-form-error").textContent = "";
  $("#student-dialog-title").textContent = student ? "Edit student" : "Add student";
  form.elements.id.value = student?.id || "";
  if (student) {
    form.elements.name.value = student.name;
    form.elements.enrollment_no.value = student.enrollment_no;
    form.elements.email.value = student.email;
    form.elements.class_id.value = student.class_id;
  }
  dialog.showModal();
}

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((button) =>
    button.addEventListener("click", () => showView(button.dataset.view)));
  $("#student-search").addEventListener("input", () => refreshStudents().catch((error) => showNotice(error.message, true)));
  $("#class-filter").addEventListener("change", () => refreshStudents().catch((error) => showNotice(error.message, true)));
  $("#student-sort").addEventListener("change", () => refreshStudents().catch((error) => showNotice(error.message, true)));
  $("#add-student-button").addEventListener("click", () => openStudentDialog());
  $("#close-dialog").addEventListener("click", () => $("#student-dialog").close());
  $("#cancel-dialog").addEventListener("click", () => $("#student-dialog").close());

  $("#students-body").addEventListener("click", async (event) => {
    const edit = event.target.closest("[data-edit]");
    const remove = event.target.closest("[data-delete]");
    if (edit) openStudentDialog(studentsCache.find((item) => item.id === Number(edit.dataset.edit)));
    if (remove && window.confirm("Delete this student and their records?")) {
      try {
        await api(`/api/students/${remove.dataset.delete}`, {method: "DELETE"});
        await loadBootstrapData();
        showNotice("Student and related records deleted.");
      } catch (error) { showNotice(error.message, true); }
    }
  });

  $("#student-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = {
      name: form.elements.name.value, enrollment_no: form.elements.enrollment_no.value,
      email: form.elements.email.value, class_id: Number(form.elements.class_id.value)
    };
    const id = form.elements.id.value;
    try {
      await api(id ? `/api/students/${id}` : "/api/students", {
        method: id ? "PUT" : "POST", body: JSON.stringify(payload)
      });
      $("#student-dialog").close();
      await loadBootstrapData();
      showNotice(id ? "Student updated." : "Student added.");
    } catch (error) { $("#student-form-error").textContent = error.message; }
  });

  $("#attendance-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await api("/api/attendance", {method: "POST", body: JSON.stringify({
        student_id: Number(form.get("student_id")), attendance_date: form.get("attendance_date"),
        status: form.get("status")
      })});
      await Promise.all([loadAttendance(), loadDashboard()]);
      showNotice("Attendance saved.");
    } catch (error) { showNotice(error.message, true); }
  });

  $("#marks-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const result = await api("/api/marks", {method: "POST", body: JSON.stringify({
        student_id: Number(form.get("student_id")), subject_id: Number(form.get("subject_id")),
        score: Number(form.get("score"))
      })});
      await loadMarks();
      showNotice(`Marks saved. Calculated grade: ${result.grade}`);
    } catch (error) { showNotice(error.message, true); }
  });

  $("#logout").addEventListener("click", async () => {
    try { await api("/api/logout", {method: "POST"}); window.location.href = "/"; }
    catch (error) { showNotice(error.message, true); }
  });
  $("#theme-toggle").addEventListener("click", () => {
    document.body.classList.toggle("dark");
    localStorage.setItem("campusdesk-theme", document.body.classList.contains("dark") ? "dark" : "light");
  });
}

async function start() {
  try {
    const me = await api("/api/me");
    currentUser = me.user;
    csrfToken = me.csrf_token;
    if (localStorage.getItem("campusdesk-theme") === "dark") document.body.classList.add("dark");
    $("#user-label").textContent = `${currentUser.username} · ${currentUser.role}`;
    $("#user-avatar").textContent = currentUser.username.slice(0, 1).toUpperCase();
    $("#welcome-name").textContent = currentUser.username;
    $("#today-label").textContent = new Date().toLocaleDateString(undefined,
      {weekday: "short", month: "short", day: "numeric", year: "numeric"});
    if (currentUser.role === "student") {
      document.querySelector('[data-view="students"]').textContent = "♙ My record";
      $("#add-student-button").hidden = true;
      document.querySelector('[data-view="attendance"]').hidden = true;
      document.querySelector('[data-view="marks"]').hidden = true;
      $("#attendance-form").hidden = true;
      $("#marks-form").hidden = true;
    }
    if (currentUser.role === "teacher") $("#add-student-button").hidden = true;
    bindEvents();
    await Promise.all([loadBootstrapData(), loadDashboard()]);
    document.querySelectorAll(".student-options").forEach((select) => {
      if (currentUser.role === "student") select.disabled = true;
    });
    document.querySelectorAll(".class-options").forEach((select) => {
      if (currentUser.role !== "admin") select.disabled = true;
    });
  } catch (_error) {
    window.location.href = "/";
  }
}

start();
