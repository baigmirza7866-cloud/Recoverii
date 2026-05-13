const header = document.getElementById('header');
window.addEventListener('scroll', () => {
  header.classList.toggle('scrolled', window.scrollY > 60);
});

function toggleMenu() {
  document.getElementById('navLinks').classList.toggle('open');
}
function closeMenu() {
  document.getElementById('navLinks').classList.remove('open');
}
document.addEventListener('click', (e) => {
  if (!document.querySelector('.nav').contains(e.target)) closeMenu();
});

document.addEventListener('DOMContentLoaded', () => {

  // Highlight today's hours row
  const days = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  const today = days[new Date().getDay()];
  document.querySelectorAll('.hours-table tr').forEach(row => {
    if (row.cells[0] && row.cells[0].textContent.trim() === today) {
      row.classList.add('today');
    }
  });

  // Animate elements into view
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.08 });

  document.querySelectorAll('.service-card, .platform-card, .gallery-item').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(18px)';
    el.style.transition = 'opacity .4s ease, transform .4s ease';
    observer.observe(el);
  });

});