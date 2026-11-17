const navToggle = document.querySelector(".nav-toggle");
const nav = document.querySelector("#site-nav");
if (navToggle && nav) {
  navToggle.addEventListener("click", () => {
    const open = nav.classList.toggle("is-open");
    navToggle.setAttribute("aria-expanded", open ? "true" : "false");
  });
}

document.querySelectorAll("[data-toggle-password]").forEach((button) => {
  button.addEventListener("click", () => {
    const input = document.getElementById(button.getAttribute("data-toggle-password"));
    if (!input) return;
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    button.textContent = showing ? "Show" : "Hide";
  });
});

function isLetter(char) {
  return /^\p{L}$/u.test(char);
}

function nameError(value) {
  const cleaned = value.trim().replace(/\s+/g, " ");
  if (!cleaned) return "Enter your name.";
  if ([...cleaned].some((char) => char !== " " && !isLetter(char))) {
    return "Name cannot contain numbers or special characters.";
  }
  if (cleaned.length < 2) return "Enter your full name using letters only.";
  return "";
}

function usernameError(value) {
  if (!value.trim()) return "Enter a username.";
  if (/\s/.test(value)) return "Username cannot contain spaces.";
  if (/^\p{N}/u.test(value)) return "Username cannot start with a number.";
  if (!isLetter(value[0])) return "Username cannot start with a special character.";
  if (value.length < 3) return "Username must be at least 3 characters.";
  if (value.length > 20) return "Username must be 20 characters or fewer.";
  if ([...value].some((char) => !isLetter(char) && !/^\p{N}$/u.test(char))) {
    return "Username can only contain letters and numbers.";
  }
  if (value.toLowerCase() === "admin") return "This username is reserved.";
  return "";
}

function emailError(value) {
  const email = value.trim();
  if (!email) return "Enter an email address.";
  if (!/^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/.test(email) || email.includes("..")) {
    return "Enter a valid email address.";
  }
  return "";
}

function phoneError(value) {
  const phone = value.trim().replace(/[\s\-().]/g, "");
  if (!phone) return "Enter a phone number.";
  const rwanda = /^(?:\+250|250|0)7[2389]\d{7}$/;
  const intl = /^\+[1-9]\d{8,14}$/;
  if (rwanda.test(phone) || intl.test(phone)) return "";
  return "Enter a valid phone number: 072, 073, 078, or 079, or an international number starting with +.";
}

function passwordError(password, confirm, required) {
  if (!password && !confirm && !required) return "";
  if (!password || password.trim() === "" || password.length < 6) {
    return "Password must be at least 6 characters.";
  }
  if (password !== confirm) return "Passwords do not match.";
  return "";
}

function showError(form, name, message) {
  const field = form.querySelector(`[name="${name}"]`);
  if (!field) return;
  const label = field.closest("label") || field.parentElement;
  let note = label.querySelector(".field-error");
  if (!note) {
    note = document.createElement("small");
    note.className = "field-error";
    label.append(note);
  }
  note.textContent = message;
  if (message) field.setAttribute("aria-invalid", "true");
  else field.removeAttribute("aria-invalid");
}

document.querySelectorAll("form[data-rules]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const rules = form.dataset.rules;
    let blocked = false;
    if (rules === "symptoms") {
      const chosen = form.querySelectorAll('input[name="symptoms"]:checked');
      const note = document.querySelector("#symptoms-error");
      if (!chosen.length) {
        blocked = true;
        if (note) note.textContent = "Select at least one symptom.";
      } else if (note && note.textContent === "Select at least one symptom.") {
        note.textContent = "";
      }
    }
    if (rules === "account" || rules === "profile") {
      const checks = [
        ["full_name", nameError(form.full_name.value)],
        ["email", emailError(form.email.value)],
        ["phone", phoneError(form.phone.value)],
      ];
      if (rules === "account") {
        checks.push(["username", usernameError(form.username.value)]);
        checks.push(["password", passwordError(form.password.value, form.confirm_password.value, true)]);
      } else if (form.password.value || form.confirm_password.value) {
        checks.push(["password", passwordError(form.password.value, form.confirm_password.value, false)]);
      }
      checks.forEach(([name, message]) => {
        showError(form, name, message);
        if (message) blocked = true;
      });
    }
    if (blocked) event.preventDefault();
  });
});
