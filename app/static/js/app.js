(function () {
  "use strict";

  document.querySelectorAll(".password-toggle").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = button.closest(".password-field").querySelector("input");
      if (!input) return;
      var isPassword = input.type === "password";
      input.type = isPassword ? "text" : "password";
      button.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
      button.innerHTML = '<i class="bi ' + (isPassword ? "bi-eye-slash" : "bi-eye") + '"></i>';
    });
  });

  document.querySelectorAll("[data-demo-email]").forEach(function (button) {
    button.addEventListener("click", function () {
      var form = document.querySelector("[data-login-form]");
      if (!form) return;
      form.querySelector('input[name="email"]').value = button.dataset.demoEmail;
      form.querySelector('input[name="password"]').value = button.dataset.demoPassword;
      form.submit();
    });
  });

  document.querySelectorAll("[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  document.querySelectorAll("[data-auto-submit]").forEach(function (field) {
    field.addEventListener("change", function () {
      field.closest("form").submit();
    });
  });

  var filterToggle = document.querySelector("[data-filter-toggle]");
  if (filterToggle) {
    filterToggle.addEventListener("click", function () {
      var panel = document.querySelector(".filter-panel");
      if (panel) panel.classList.toggle("open");
    });
  }

  document.querySelectorAll("[data-topup]").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = document.querySelector("[data-topup-input]");
      if (input) {
        input.value = button.dataset.topup;
        input.focus();
      }
    });
  });

  var bookingForm = document.querySelector("[data-booking-form]");
  if (bookingForm) {
    var duration = bookingForm.querySelector('[name="duration_minutes"]');
    var quote = document.getElementById("quote-amount");
    var perHour = bookingForm.dataset.priceUnit === "per hour";
    var basePrice = parseFloat(bookingForm.dataset.price || "0");
    var updateQuote = function () {
      if (!duration || !quote) return;
      var minutes = parseInt(duration.value, 10) || 0;
      var amount = perHour ? (basePrice * minutes) / 60 : basePrice;
      quote.textContent = "K" + amount.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    };
    if (duration) duration.addEventListener("change", updateQuote);
    updateQuote();
  }

  var threadBody = document.querySelector(".thread-body");
  if (threadBody) {
    threadBody.scrollTop = threadBody.scrollHeight;
  }

  var suspendModal = document.getElementById("suspendModal");
  if (suspendModal) {
    suspendModal.addEventListener("show.bs.modal", function (event) {
      var trigger = event.relatedTarget;
      if (!trigger) return;
      var form = suspendModal.querySelector("form");
      form.action = trigger.dataset.action;
      suspendModal.querySelector(".suspend-user-name").textContent = trigger.dataset.user;
      form.querySelector('[name="reason"]').value = "";
    });
    suspendModal.addEventListener("shown.bs.modal", function () {
      suspendModal.querySelector('[name="reason"]').focus();
    });
  }

  var navCollapse = document.getElementById("mainNav");
  if (navCollapse) {
    navCollapse.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        if (window.innerWidth < 992 && navCollapse.classList.contains("show")) {
          bootstrap.Collapse.getOrCreateInstance(navCollapse).hide();
        }
      });
    });
  }
})();
