const loginForm = document.getElementById("login-form");
const loginButton = document.getElementById("login-button");
const errorBanner = document.getElementById("error-banner");

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.classList.remove("hidden");
}

function hideError() {
  errorBanner.classList.add("hidden");
  errorBanner.textContent = "";
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideError();
  loginButton.disabled = true;

  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ username, password }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Giriş başarısız.");
    }

    window.location.href = "/";
  } catch (err) {
    showError(err.message);
  } finally {
    loginButton.disabled = false;
  }
});
