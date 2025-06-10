// handroll a small custom tooltip library

let _tooltip: HTMLElement | null = null

function getTooltip(): HTMLElement {
  if (!_tooltip) {
    _tooltip = document.createElement("div")
    _tooltip.className = "tyche-tooltip"
    _tooltip.style.cssText = `
      position: absolute;
      background-color: rgba(0, 0, 0, 0.8);
      color: white;
      border-radius: 4px;
      padding: 8px;
      font-size: 12px;
      pointer-events: none;
      z-index: 10;
      display: none;
    `
    document.body.appendChild(_tooltip)
  }
  return _tooltip
}

export function showTooltip(content: string, x: number, y: number): void {
  const tooltip = getTooltip()
  tooltip.innerHTML = content
  tooltip.style.left = `${x + 10}px`
  tooltip.style.top = `${y - 28}px`
  tooltip.style.display = "block"
}

export function moveTooltip(x: number, y: number): void {
  const tooltip = getTooltip()
  tooltip.style.left = `${x + 10}px`
  tooltip.style.top = `${y - 28}px`
}

export function hideTooltip(): void {
  const tooltip = getTooltip()
  tooltip.style.display = "none"
}
