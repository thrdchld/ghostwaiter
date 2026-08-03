export function toast(message, type = "info") {
  const node = document.querySelector("#toast");
  if (!node) return;
  node.textContent = message;
  node.className = `toast ${type}`;
  clearTimeout(node.timer);
  node.timer = setTimeout(() => {
    node.className = `toast ${type} hidden`;
  }, 2800);
}
