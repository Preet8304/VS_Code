(function () {
  const revealTargets = document.querySelectorAll(".card, .stat, table, .alert");
  revealTargets.forEach((el, idx) => {
    el.classList.add("reveal", "motion-hover");
    el.style.transitionDelay = `${Math.min(idx * 40, 260)}ms`;
  });

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.12 }
  );

  revealTargets.forEach((el) => observer.observe(el));
})();
