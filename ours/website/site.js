// Shared header + footer for every page, and a light/dark switch (remembered in this browser only).
(function () {
  const pages = [
    ["index.html", "Overview"], ["commands.html", "Commands"], ["collection.html", "Data collection"],
    ["features.html", "Features + R"], ["reality.html", "Real world"], ["status.html", "Status + checks"],
  ];
  const here = location.pathname.split("/").pop() || "index.html";
  try { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
  const header = document.createElement("header");
  header.className = "site";
  header.innerHTML = '<div class="in"><a class="brand" href="index.html">Covert head-gesture commands</a><nav>' +
    pages.map(([h, t]) => `<a href="${h}"${h === here ? ' class="on"' : ""}>${t}</a>`).join("") +
    '</nav><button class="toggle" type="button" aria-label="Switch light or dark">Light / dark</button></div>';
  document.body.prepend(header);
  header.querySelector(".toggle").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", document.documentElement.dataset.theme); } catch (e) {}
  });
  document.querySelectorAll("svg.diagram").forEach((svg) => {   // wide diagrams scroll inside their own box on phones
    const box = document.createElement("div");
    box.className = "dia";
    svg.parentNode.insertBefore(box, svg);
    box.appendChild(svg);
  });
  const i = pages.findIndex(([h]) => h === here);
  const main = document.querySelector("main");
  if (main && i >= 0) {
    const nav = document.createElement("div");
    nav.className = "next";
    nav.innerHTML = (i > 0 ? `<a href="${pages[i - 1][0]}">← ${pages[i - 1][1]}</a>` : "<span></span>") +
      (i < pages.length - 1 ? `<a href="${pages[i + 1][0]}">${pages[i + 1][1]} →</a>` : "<span></span>");
    main.appendChild(nav);
  }
  const f = document.createElement("footer");
  f.textContent = "CS724, IIT Kanpur, Group 6. Numbers come from the files named on each page (ours/algorithm/results). Last updated 2026-11-08.";
  document.body.appendChild(f);
})();
