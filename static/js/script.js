// Global JavaScript functions can be added here
document.addEventListener('DOMContentLoaded', function() {
  // Initialize tooltips
  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.map(function (tooltipTriggerEl) {
      return new bootstrap.Tooltip(tooltipTriggerEl);
  });
  
  // Add active class to current page in navbar
  const currentPage = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-link').forEach(link => {
      if (link.getAttribute('href') === currentPage) {
          link.classList.add('active');
          link.innerHTML = `<i class="${link.querySelector('i').className}"></i> ${link.textContent}`;
      }
  });
  
  // Scroll to top button
  const scrollToTopBtn = document.createElement('button');
  scrollToTopBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
  scrollToTopBtn.className = 'btn btn-success btn-lg scroll-to-top';
  scrollToTopBtn.style.position = 'fixed';
  scrollToTopBtn.style.bottom = '20px';
  scrollToTopBtn.style.right = '20px';
  scrollToTopBtn.style.display = 'none';
  scrollToTopBtn.style.zIndex = '99';
  scrollToTopBtn.style.borderRadius = '50%';
  scrollToTopBtn.style.width = '50px';
  scrollToTopBtn.style.height = '50px';
  scrollToTopBtn.style.padding = '0';
  document.body.appendChild(scrollToTopBtn);
  
  window.addEventListener('scroll', function() {
      if (window.pageYOffset > 300) {
          scrollToTopBtn.style.display = 'block';
      } else {
          scrollToTopBtn.style.display = 'none';
      }
  });
  
  scrollToTopBtn.addEventListener('click', function() {
      window.scrollTo({
          top: 0,
          behavior: 'smooth'
      });
  });
});