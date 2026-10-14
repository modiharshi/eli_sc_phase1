document.addEventListener('click', function (e) {
  var b = e.target.closest('[data-copy]'); if (!b) return;
  var v = b.dataset.copyUrl ? location.origin + b.dataset.copyUrl : b.dataset.copy;
  (navigator.clipboard ? navigator.clipboard.writeText(v) : Promise.reject()).then(function () { var o = b.textContent; b.textContent = 'Copied'; setTimeout(function () { b.textContent = o; }, 1200); },
    function () { window.prompt('Copy this:', v); });
});
