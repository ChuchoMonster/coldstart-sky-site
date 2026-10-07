/* ColdStart — scroll-flight engine.
   Fixed stage + tall .journey-track for scroll distance. One scrubbed master
   timeline; no ScrollTrigger pinning (pin + Lenis = jank). Modules are read
   from DOM order — add a <section class="module" data-module> and the engine
   picks it up; no JS edits needed. */

(() => {
  gsap.registerPlugin(ScrollTrigger);

  const docEl = document.documentElement;
  const body = document.body;
  const track = document.querySelector(".journey-track");
  const modules = gsap.utils.toArray(".module");
  const bands = gsap.utils.toArray(".sky-band");
  const skyConfig = JSON.parse(body.dataset.sky || "[]");
  const readout = document.querySelector(".altimeter-readout");
  const ticksWrap = document.querySelector(".altimeter-ticks");
  const progressbar = document.querySelector(".progressbar");

  const PEAK_ALT = parseInt(body.dataset.peakAlt || "38000", 10);
  const VH_PER_MODULE = 130; // scroll fuel per module
  const PERSPECTIVE = 1200;
  const Z_FAR = -3500;
  const Z_NEAR = -250;
  const Z_EXIT = 850; // clamped below PERSPECTIVE — never cross the camera plane (Safari)

  const fmtAlt = (m) => `${Math.round(m).toLocaleString("en-US").padStart(6, " ")} M`;

  /* ---------- lazy sky-band loading ---------- */
  const safePlay = (v) => {
    if (!v) return;
    const p = v.play();
    if (p) p.catch(() => {});
  };
  const loadedBands = new Set();
  function loadBand(k) {
    const v = bands[k];
    if (!v || loadedBands.has(k)) return;
    loadedBands.add(k);
    v.querySelectorAll("source[data-src]").forEach((s) => (s.src = s.dataset.src));
    v.load();
  }

  /* ---------- altimeter ticks ---------- */
  const chapters = [];
  modules.forEach((m, i) => {
    const name = m.dataset.chapter;
    if (name) chapters.push({ name, moduleIndex: i });
  });
  chapters.push({ name: "Landing", moduleIndex: modules.length, landing: true });

  let tickButtons = [];
  if (ticksWrap) {
    chapters.forEach((ch, ci) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("aria-label", `Go to ${ch.name}`);
      btn.addEventListener("click", () => scrollToChapter(ci));
      li.appendChild(btn);
      ticksWrap.appendChild(li);
    });
    tickButtons = [...ticksWrap.querySelectorAll("button")];
  }

  let flight = null; // { st, lenis, D }

  function scrollToChapter(ci) {
    const ch = chapters[ci];
    let target;
    if (ch.landing || !flight) {
      target = document.querySelector(".landing").offsetTop;
    } else {
      const { st, D } = flight;
      target = st.start + ((ch.moduleIndex + 0.45) / D) * (st.end - st.start);
    }
    if (flight && flight.lenis) flight.lenis.scrollTo(target);
    else window.scrollTo({ top: target, behavior: "smooth" });
  }

  function updateHud(progress, modIndex) {
    if (readout) readout.textContent = fmtAlt(PEAK_ALT * Math.min(progress / 0.92, 1));
    tickButtons.forEach((b, ci) => {
      const ch = chapters[ci];
      const next = chapters[ci + 1];
      const active = !ch.landing && modIndex >= ch.moduleIndex && (!next || modIndex < next.moduleIndex);
      b.setAttribute("aria-current", active ? "true" : "false");
    });
  }

  /* ====================================================
     Branches
     ==================================================== */
  const mm = gsap.matchMedia();

  /* ----- full flight: desktop, motion OK ----- */
  mm.add("(min-width: 768px) and (prefers-reduced-motion: no-preference)", () => {
    docEl.classList.remove("is-static");

    const lenis = new Lenis({ autoRaf: false });
    lenis.on("scroll", ScrollTrigger.update);
    const raf = (time) => lenis.raf(time * 1000);
    gsap.ticker.add(raf);
    gsap.ticker.lagSmoothing(0);

    const D = modules.length; // 1 timeline unit per module
    track.style.height = `${D * VH_PER_MODULE}vh`;

    /* initial module placement — weaving flight path */
    modules.forEach((m, i) => {
      const isHero = m.dataset.module === "hero";
      const x = m.dataset.x !== undefined ? parseFloat(m.dataset.x) : isHero ? 0 : i % 2 ? 12 : -12;
      const y = m.dataset.y !== undefined ? parseFloat(m.dataset.y) : isHero ? 0 : i % 3 === 0 ? 8 : -6;
      gsap.set(m, {
        xPercent: -50,
        yPercent: -50,
        x: `${x}vw`,
        y: `${y}vh`,
        z: isHero ? 0 : Z_FAR,
        autoAlpha: isHero ? 1 : 0,
        rotateX: isHero ? 0 : 5,
        rotateY: isHero ? 0 : i % 2 ? -4 : 4,
        "--fog": isHero ? 0 : 0.9,
      });
    });

    const tl = gsap.timeline({ paused: false });

    modules.forEach((m, i) => {
      const t0 = i;
      if (m.dataset.module === "hero") {
        // already on screen — dwell, then fly past
        tl.to(m, { z: Z_EXIT, autoAlpha: 0, ease: "power2.in", duration: 0.4 }, t0 + 0.55);
        tl.to(".scroll-cue", { autoAlpha: 0, duration: 0.15 }, t0 + 0.05);
      } else {
        // approach (35%) → dwell (40%, the reading window) → depart (25%)
        tl.to(m, { z: Z_NEAR, autoAlpha: 1, rotateX: 0, rotateY: 0, "--fog": 0.15, ease: "power2.out", duration: 0.35 }, t0 - 0.1);
        tl.to(m, { z: 0, "--fog": 0, ease: "none", duration: 0.4 }, t0 + 0.25);
        tl.to(m, { z: Z_EXIT, autoAlpha: 0, ease: "power2.in", duration: 0.25 }, t0 + 0.65);
      }
      if (m.dataset.flare !== undefined) {
        tl.to(".flare", { opacity: 0.9, duration: 0.3 }, t0 + 0.05);
        tl.to(".flare", { opacity: 0, duration: 0.25 }, t0 + 0.7);
      }
    });

    /* sky: gradient climb + haze thinning across the whole flight */
    tl.fromTo(".sky-gradient", { y: "-10vh" }, { y: "10vh", ease: "none", duration: D }, 0);
    tl.to(".haze", { opacity: 0.03, ease: "none", duration: D }, 0);

    /* sky band crossfades at chapter boundaries */
    if (bands.length && skyConfig.length) {
      gsap.set(bands, { opacity: 0 });
      gsap.set(bands[0], { opacity: 1 });
      bands.forEach((v) => gsap.fromTo(v, { yPercent: 3, scale: 1.06 }, { yPercent: -3, scale: 1, ease: "none", scrollTrigger: { trigger: track, start: "top top", end: "bottom bottom", scrub: true } }));
      for (let k = 0; k < Math.min(bands.length, skyConfig.length) - 1; k++) {
        const p = skyConfig[k].until * D;
        const w = 0.16 * D;
        tl.to(bands[k], { opacity: 0, duration: w, onComplete: () => bands[k].pause(), onReverseComplete: () => safePlay(bands[k]) }, p - w / 2);
        tl.to(bands[k + 1], { opacity: 1, duration: w, onStart: () => safePlay(bands[k + 1]) }, p - w / 2);
      }
    }

    const st = ScrollTrigger.create({
      trigger: track,
      start: "top top",
      end: "bottom bottom",
      scrub: 0.6,
      animation: tl,
      onUpdate: (self) => {
        const p = self.progress;
        updateHud(p, Math.max(0, Math.min(D - 1, Math.round(p * D - 0.45))));
        // lazy-load upcoming bands
        skyConfig.forEach((b, k) => {
          const bandStart = k === 0 ? 0 : skyConfig[k - 1].until;
          if (p > bandStart - 0.15) loadBand(k);
        });
      },
    });

    flight = { st, lenis, D };
    loadBand(0);
    if (bands[0]) bands[0].addEventListener("loadeddata", () => safePlay(bands[0]), { once: true });

    /* descent: altitude counts back down as the landing scrolls up */
    const descent = ScrollTrigger.create({
      trigger: ".landing",
      start: "top bottom",
      end: "top top",
      onUpdate: (self) => {
        if (readout) readout.textContent = fmtAlt(PEAK_ALT * (1 - self.progress));
        if (self.progress > 0.05) tickButtons.forEach((b, ci) => b.setAttribute("aria-current", chapters[ci].landing ? "true" : "false"));
      },
    });

    /* keyboard: keep focused modules on camera */
    const onFocus = (e) => {
      const m = e.target.closest(".module");
      if (!m) return;
      const i = modules.indexOf(m);
      if (i >= 0) lenis.scrollTo(st.start + ((i + 0.45) / D) * (st.end - st.start), { duration: 0.8 });
    };
    document.addEventListener("focusin", onFocus);

    /* hero entrance */
    gsap.from(".module--hero > *", { y: 26, autoAlpha: 0, stagger: 0.08, duration: 0.9, ease: "power3.out", delay: 0.15 });

    return () => {
      document.removeEventListener("focusin", onFocus);
      gsap.ticker.remove(raf);
      lenis.destroy();
      st.kill();
      descent.kill();
      tl.kill();
      flight = null;
    };
  });

  /* ----- static branch: mobile or reduced motion ----- */
  mm.add("(max-width: 767px), (prefers-reduced-motion: reduce)", (ctx) => {
    docEl.classList.add("is-static");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const onScroll = () => {
      const max = docEl.scrollHeight - window.innerHeight;
      if (progressbar) progressbar.style.width = `${(window.scrollY / max) * 100}%`;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    const tweens = [];
    if (!reduced) {
      modules.forEach((m) => {
        if (m.dataset.module === "hero") return;
        tweens.push(
          gsap.fromTo(m, { opacity: 0 }, { opacity: 1, duration: 0.7, ease: "power2.out", scrollTrigger: { trigger: m, start: "top 88%" } })
        );
      });
    }

    return () => {
      window.removeEventListener("scroll", onScroll);
      tweens.forEach((t) => {
        t.scrollTrigger && t.scrollTrigger.kill();
        t.kill();
      });
      docEl.classList.remove("is-static");
    };
  });
})();
