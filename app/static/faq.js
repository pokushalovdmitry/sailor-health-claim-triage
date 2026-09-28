// Accordion: only one item open at a time. Clicking an open question closes
// it; clicking a different question closes whichever was open and opens the
// clicked one.
document.querySelectorAll(".accordion-question").forEach((btn) => {
  btn.addEventListener("click", () => {
    const item = btn.closest(".accordion-item");
    const wasOpen = item.classList.contains("open");

    document.querySelectorAll(".accordion-item.open").forEach((openItem) => {
      openItem.classList.remove("open");
      openItem.querySelector(".accordion-question").setAttribute("aria-expanded", "false");
    });

    if (!wasOpen) {
      item.classList.add("open");
      btn.setAttribute("aria-expanded", "true");
    }
  });
});
