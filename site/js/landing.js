/* Lazy Cal.com inline embed — script loads only when the landing nears the
   viewport. The plain "Book a call" fallback link stays until the embed's
   iframe actually renders, so a failed load never strands the visitor. */

(() => {
  const shell = document.querySelector(".cal-shell");
  if (!shell || !shell.dataset.calLink || !("IntersectionObserver" in window)) return;

  let started = false;
  const io = new IntersectionObserver(
    (entries) => {
      if (started || !entries.some((e) => e.isIntersecting)) return;
      started = true;
      io.disconnect();

      /* official Cal.com embed loader */
      (function (C, A, L) {
        let p = function (a, ar) { a.q.push(ar); };
        let d = C.document;
        C.Cal = C.Cal || function () {
          let cal = C.Cal, ar = arguments;
          if (!cal.loaded) {
            cal.ns = {}; cal.q = cal.q || [];
            d.head.appendChild(d.createElement("script")).src = A;
            cal.loaded = true;
          }
          if (ar[0] === L) {
            const api = function () { p(api, arguments); };
            const namespace = ar[1];
            api.q = api.q || [];
            if (typeof namespace === "string") { cal.ns[namespace] = cal.ns[namespace] || api; p(cal.ns[namespace], ar); p(cal, ["initNamespace", namespace]); }
            else p(cal, ar);
            return;
          }
          p(cal, ar);
        };
      })(window, "https://app.cal.com/embed/embed.js", "init");

      Cal("init", { origin: "https://cal.com" });

      const mount = document.createElement("div");
      mount.id = "cal-inline";
      mount.style.cssText = "width:100%;height:100%;min-height:540px;overflow:auto;";
      shell.appendChild(mount);

      Cal("inline", {
        elementOrSelector: "#cal-inline",
        calLink: shell.dataset.calLink,
        layout: "month_view",
      });

      /* hide the fallback only once the embed iframe is really there */
      const watch = setInterval(() => {
        if (mount.querySelector("iframe")) {
          const fb = shell.querySelector(".cal-fallback");
          if (fb) fb.style.display = "none";
          clearInterval(watch);
        }
      }, 400);
      setTimeout(() => clearInterval(watch), 15000);
    },
    { rootMargin: "100% 0px" }
  );
  io.observe(shell);
})();
