for (const label of document.querySelectorAll(".timeline-label[data-depth]")) {
    const depth = Number(label.dataset.depth || 0);
    label.style.paddingLeft = `${depth * 18}px`;
}

for (const bar of document.querySelectorAll(".timeline-bar[data-left][data-width]")) {
    bar.style.left = `${bar.dataset.left}%`;
    bar.style.width = `${bar.dataset.width}%`;
}
