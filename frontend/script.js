// Mock student data
const mockStudentData = [
  {
    user_id: "001",
    name: "Alice Johnson",
    email: "alice@university.edu",
    class: "Computer Science",
    num_events_attended: 3,
    num_absences: 1,
    num_late_arrivals: 0,
    last_attended_date: "2024-01-15",
    events_attended: ["Tech Talk 2023", "Workshop 2024", "Networking Event"],
    response: "yes",
  },
  {
    user_id: "002",
    name: "Bob Smith",
    email: "bob@university.edu",
    class: "Engineering",
    num_events_attended: 1,
    num_absences: 0,
    num_late_arrivals: 2,
    last_attended_date: "2023-12-10",
    events_attended: ["Workshop 2023"],
    response: "yes",
  },
  {
    user_id: "003",
    name: "Carol Davis",
    email: "carol@university.edu",
    class: "Business",
    num_events_attended: 0,
    num_absences: 0,
    num_late_arrivals: 0,
    last_attended_date: null,
    events_attended: [],
    response: "yes",
  },
  {
    user_id: "004",
    name: "David Wilson",
    email: "david@university.edu",
    class: "Mathematics",
    num_events_attended: 2,
    num_absences: 2,
    num_late_arrivals: 1,
    last_attended_date: "2023-11-20",
    events_attended: ["Tech Talk 2023", "Workshop 2023"],
    response: "no",
  },
  {
    user_id: "005",
    name: "Eva Martinez",
    email: "eva@university.edu",
    class: "Physics",
    num_events_attended: 0,
    num_absences: 0,
    num_late_arrivals: 1,
    last_attended_date: null,
    events_attended: [],
    response: "yes",
  },
]

// Application state
let appState = {
  currentStep: "upload",
  signupFile: null,
  historicalFile: null,
  eventName: "",
  eventCapacity: 0,
  studentData: [...mockStudentData],
  selectedAttendees: [],
  eligibleStudents: [],
}

// DOM elements
const steps = {
  upload: document.getElementById("upload-step"),
  config: document.getElementById("config-step"),
  database: document.getElementById("database-step"),
  selection: document.getElementById("selection-step"),
  results: document.getElementById("results-step"),
}

// Initialize the application
document.addEventListener("DOMContentLoaded", () => {
  initializeEventListeners()
  showStep("upload")
})

function initializeEventListeners() {
  // File upload handlers
  document.getElementById("signup-file").addEventListener("change", handleSignupFileChange)
  document.getElementById("historical-file").addEventListener("change", handleHistoricalFileChange)

  // Navigation buttons
  document.getElementById("proceed-config").addEventListener("click", proceedToConfiguration)
  document.getElementById("back-upload").addEventListener("click", () => showStep("upload"))
  document.getElementById("process-selection").addEventListener("click", validateAndProceedToDatabase)
  document.getElementById("proceed-selection").addEventListener("click", () => showStep("selection"))
  document.getElementById("run-selection").addEventListener("click", runAttendeeSelection)
  document.getElementById("generate-results").addEventListener("click", () => showStep("results"))
  document.getElementById("reset-app").addEventListener("click", resetApplication)

  // Search functionality
  document.getElementById("search-students").addEventListener("input", handleStudentSearch)

  // Download buttons
  document.getElementById("download-selected").addEventListener("click", downloadSelectedAttendees)
  document.getElementById("download-ranking").addEventListener("click", downloadAllEligible)
  document.getElementById("download-database").addEventListener("click", downloadUpdatedDatabase)
}

function showStep(stepName) {
  // Hide all steps
  Object.values(steps).forEach((step) => step.classList.remove("active"))

  // Show current step
  steps[stepName].classList.add("active")
  appState.currentStep = stepName

  // Update step-specific content
  if (stepName === "database") {
    updateDatabaseView()
  } else if (stepName === "selection") {
    updateSelectionView()
  } else if (stepName === "results") {
    updateResultsView()
  }
}

function handleSignupFileChange(event) {
  const file = event.target.files[0]
  const statusElement = document.getElementById("signup-status")

  if (file && file.type === "text/csv") {
    appState.signupFile = file
    statusElement.textContent = `📄 ${file.name}`
    statusElement.style.display = "flex"
    updateProceedButton()
    showAlert("Sign-up file loaded successfully", "success")
  } else {
    statusElement.style.display = "none"
    showAlert("Please select a valid CSV file", "error")
  }
}

function handleHistoricalFileChange(event) {
  const file = event.target.files[0]
  const statusElement = document.getElementById("historical-status")

  if (file && file.type === "text/csv") {
    appState.historicalFile = file
    statusElement.textContent = `📄 ${file.name}`
    statusElement.style.display = "flex"
    showAlert("Historical database file loaded successfully", "success")
  } else {
    statusElement.style.display = "none"
    showAlert("Please select a valid CSV file", "error")
  }
}

function updateProceedButton() {
  const proceedButton = document.getElementById("proceed-config")
  proceedButton.disabled = !appState.signupFile
}

function showAlert(message, type = "info") {
  const alertElement = document.getElementById("upload-alert")
  alertElement.textContent = message
  alertElement.className = `alert ${type === "error" ? "alert-error" : ""}`
  alertElement.classList.remove("hidden")

  setTimeout(() => {
    alertElement.classList.add("hidden")
  }, 3000)
}

function proceedToConfiguration() {
  if (!appState.signupFile) {
    showAlert("Please upload a sign-up file first", "error")
    return
  }
  showStep("config")
}

function validateAndProceedToDatabase() {
  const eventName = document.getElementById("event-name").value.trim()
  const eventCapacity = document.getElementById("event-capacity").value
  const errorElement = document.getElementById("config-error")

  errorElement.classList.add("hidden")

  if (!eventName) {
    errorElement.textContent = "Please enter an event name"
    errorElement.classList.remove("hidden")
    return
  }

  const capacity = Number.parseInt(eventCapacity)
  if (!eventCapacity || isNaN(capacity) || capacity <= 0) {
    errorElement.textContent = "Please enter a valid positive number for event capacity"
    errorElement.classList.remove("hidden")
    return
  }

  appState.eventName = eventName
  appState.eventCapacity = capacity
  showStep("database")
}

function updateDatabaseView() {
  const infoElement = document.getElementById("database-info")
  infoElement.textContent = `Event: ${appState.eventName} | Capacity: ${appState.eventCapacity} | Total Students: ${appState.studentData.length}`

  renderStudentsTable(appState.studentData)
}

function renderStudentsTable(students) {
  const tbody = document.querySelector("#students-table tbody")
  tbody.innerHTML = ""

  students.forEach((student) => {
    const row = document.createElement("tr")
    row.innerHTML = `
            <td>${student.name}</td>
            <td>${student.email}</td>
            <td>${student.class}</td>
            <td><span class="badge ${student.response.toLowerCase() === "yes" ? "badge-yes" : "badge-no"}">${student.response}</span></td>
            <td>${student.num_events_attended}</td>
            <td>${student.num_absences}</td>
            <td>${student.num_late_arrivals}</td>
            <td>${student.last_attended_date || "Never"}</td>
        `
    tbody.appendChild(row)
  })
}

function handleStudentSearch(event) {
  const searchTerm = event.target.value.toLowerCase()
  const filteredStudents = appState.studentData.filter(
    (student) =>
      student.name.toLowerCase().includes(searchTerm) ||
      student.email.toLowerCase().includes(searchTerm) ||
      student.class.toLowerCase().includes(searchTerm),
  )
  renderStudentsTable(filteredStudents)
}

function updateSelectionView() {
  const infoElement = document.getElementById("selection-info")
  infoElement.textContent = `Event: ${appState.eventName} | Capacity: ${appState.eventCapacity}`
}

function runAttendeeSelection() {
  // Filter eligible students (those who responded "yes")
  const eligible = appState.studentData.filter((student) => student.response.toLowerCase() === "yes")

  // Shuffle for random selection
  const shuffled = [...eligible].sort(() => Math.random() - 0.5)

  // Select up to capacity
  const selected = shuffled.slice(0, appState.eventCapacity)

  appState.eligibleStudents = eligible
  appState.selectedAttendees = selected

  // Hide ready card and show results
  document.getElementById("selection-ready").classList.add("hidden")
  document.getElementById("selection-results").classList.remove("hidden")
  document.getElementById("selection-complete").classList.remove("hidden")

  // Update selected count
  document.getElementById("selected-count").textContent = `Students selected for the event (${selected.length})`

  // Render selected attendees
  renderAttendeeList("selected-list", selected, true)

  // Render all eligible students
  renderAttendeeList("eligible-list", eligible, false)
}

function renderAttendeeList(containerId, students, showSelected) {
  const container = document.getElementById(containerId)
  container.innerHTML = ""

  students.forEach((student, index) => {
    const isSelected = showSelected || appState.selectedAttendees.some((s) => s.user_id === student.user_id)
    const div = document.createElement("div")
    div.className = `attendee-item ${isSelected && index < appState.eventCapacity ? "selected" : ""}`

    div.innerHTML = `
            <div class="attendee-info">
                <h4>${student.name}</h4>
                <p>${student.email} • ${student.class}</p>
            </div>
            <div class="attendee-rank">
                ${
                  showSelected
                    ? `<span class="rank-badge">Rank #${index + 1}</span>`
                    : isSelected && index < appState.eventCapacity
                      ? "✅"
                      : "❌"
                }
            </div>
        `

    container.appendChild(div)
  })
}

function updateResultsView() {
  const totalSignups = appState.studentData.length
  const eligibleCount = appState.eligibleStudents.length
  const selectedCount = appState.selectedAttendees.length
  const selectionRate = eligibleCount > 0 ? Math.round((selectedCount / eligibleCount) * 100) : 0
  const currentDate = new Date().toLocaleDateString()

  // Update statistics
  document.getElementById("total-signups").textContent = totalSignups
  document.getElementById("eligible-count").textContent = eligibleCount
  document.getElementById("selected-final-count").textContent = selectedCount
  document.getElementById("selection-rate").textContent = `${selectionRate}%`

  // Update summary
  document.getElementById("summary-event-name").textContent = appState.eventName
  document.getElementById("summary-capacity").textContent = appState.eventCapacity
  document.getElementById("summary-date").textContent = currentDate
  document.getElementById("summary-total").textContent = totalSignups
  document.getElementById("summary-eligible").textContent = eligibleCount
  document.getElementById("summary-selected").textContent = selectedCount
  document.getElementById("summary-waitlisted").textContent = eligibleCount - selectedCount

  // Update final event name
  document.getElementById("final-event-name").textContent = `Final list of students selected for ${appState.eventName}`

  // Render final results table
  renderFinalResultsTable()
}

function renderFinalResultsTable() {
  const tbody = document.querySelector("#final-results-table tbody")
  tbody.innerHTML = ""

  appState.selectedAttendees.forEach((student, index) => {
    const row = document.createElement("tr")
    row.innerHTML = `
            <td>#${index + 1}</td>
            <td>${student.name}</td>
            <td>${student.email}</td>
            <td>${student.class}</td>
        `
    tbody.appendChild(row)
  })
}

function generateCSVContent(data) {
  if (data.length === 0) return ""

  const headers = Object.keys(data[0]).join(",")
  const rows = data
    .map((row) =>
      Object.values(row)
        .map((value) => (typeof value === "string" && value.includes(",") ? `"${value}"` : value))
        .join(","),
    )
    .join("\n")

  return `${headers}\n${rows}`
}

function downloadCSV(content, filename) {
  const blob = new Blob([content], { type: "text/csv" })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}

function downloadSelectedAttendees() {
  const content = generateCSVContent(appState.selectedAttendees)
  const filename = `${appState.eventName.replace(/\s+/g, "_")}_selected_attendees.csv`
  downloadCSV(content, filename)
}

function downloadAllEligible() {
  const content = generateCSVContent(appState.eligibleStudents)
  const filename = `${appState.eventName.replace(/\s+/g, "_")}_all_eligible.csv`
  downloadCSV(content, filename)
}

function downloadUpdatedDatabase() {
  // Simulate updating the database with new attendance
  const updatedData = appState.studentData.map((student) => {
    if (appState.selectedAttendees.some((selected) => selected.user_id === student.user_id)) {
      return {
        ...student,
        num_events_attended: student.num_events_attended + 1,
        last_attended_date: new Date().toISOString().split("T")[0],
        events_attended: [...student.events_attended, appState.eventName],
      }
    }
    return student
  })

  const content = generateCSVContent(updatedData)
  downloadCSV(content, "updated_student_database.csv")
}

function resetApplication() {
  appState = {
    currentStep: "upload",
    signupFile: null,
    historicalFile: null,
    eventName: "",
    eventCapacity: 0,
    studentData: [...mockStudentData],
    selectedAttendees: [],
    eligibleStudents: [],
  }

  // Reset form inputs
  document.getElementById("signup-file").value = ""
  document.getElementById("historical-file").value = ""
  document.getElementById("event-name").value = ""
  document.getElementById("event-capacity").value = ""
  document.getElementById("search-students").value = ""

  // Hide status elements
  document.getElementById("signup-status").style.display = "none"
  document.getElementById("historical-status").style.display = "none"

  // Reset selection view
  document.getElementById("selection-ready").classList.remove("hidden")
  document.getElementById("selection-results").classList.add("hidden")
  document.getElementById("selection-complete").classList.add("hidden")

  // Update proceed button
  updateProceedButton()

  // Show upload step
  showStep("upload")
}
