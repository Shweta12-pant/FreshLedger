const shortDate = new Intl.DateTimeFormat("en-IN", { month: "short", day: "numeric", timeZone: "UTC" });

export function createChart(canvas, tooltip, history, prediction) {
  const data = [...history, ...prediction];
  const context = canvas.getContext("2d");
  let plot;
  let focusedPoint = null;

  function draw() {
    const { width, height } = canvas.getBoundingClientRect();
    const scale = window.devicePixelRatio || 1;
    const nextWidth = Math.round(width * scale);
    const nextHeight = Math.round(height * scale);
    if (canvas.width !== nextWidth || canvas.height !== nextHeight) {
      canvas.width = nextWidth;
      canvas.height = nextHeight;
    }
    context.setTransform(scale, 0, 0, scale, 0, 0);
    context.clearRect(0, 0, width, height);

    const styles = getComputedStyle(canvas);
    const color = (role) => styles.getPropertyValue("--" + role).trim();
    const mono = color("mono");
    const left = width < 360 ? 29 : 36;
    const right = width - 18;
    const top = 28;
    const bottom = height - 24;
    const values = data.filter((point) => point.units !== null);
    const peak = Math.max(1, ...values.map((point) => point.units));
    const step = Math.max(1, Math.ceil(peak / 4));
    const ceiling = step * 4;
    const x = (index) => left + (right - left) * index / Math.max(1, data.length - 1);
    const y = (units) => bottom - (bottom - top) * units / ceiling;
    plot = values.length ? { left, right } : null;

    context.font = "11px " + mono;
    context.fillStyle = color("muted");
    if (!plot) {
      context.textAlign = "center";
      context.fillText("No recorded sales yet", width / 2, height / 2);
      return;
    }

    if (prediction.length) {
      const boundary = (x(history.length - 1) + x(history.length)) / 2;
      context.fillStyle = color("chart-band");
      context.fillRect(boundary, top - 4, right - boundary, bottom - top + 4);
      context.fillStyle = color("accent-ink");
      context.textAlign = "left";
      context.fillText("TODAY", boundary + 5, top - 10);
      context.strokeStyle = color("chart-future");
      context.lineWidth = 1;
      context.setLineDash([3, 4]);
      line(boundary, top - 4, boundary, bottom);
      context.setLineDash([]);
    }

    context.fillStyle = color("muted");
    context.strokeStyle = color("line");
    context.lineWidth = 1;
    context.textAlign = "right";
    for (let tick = 0; tick <= ceiling; tick += step) {
      const row = y(tick);
      line(left, row, right, row);
      context.fillText(String(tick), left - 6, row + 3);
    }
    const stride = width < 340 ? 7 : width < 500 ? 5 : 4;
    for (let index = 0; index < data.length; index += stride) {
      context.textAlign = index === 0 ? "left" : index === data.length - 1 ? "right" : "center";
      context.fillText(shortDate.format(new Date(data[index].day)), x(index), height - 7);
    }

    context.fillStyle = color("chart-area");
    let runStart = 0;
    for (let index = 0; index <= history.length; index += 1) {
      if (history[index]?.units != null) continue;
      if (index - runStart > 1) {
        context.beginPath();
        context.moveTo(x(runStart), bottom);
        for (let point = runStart; point < index; point += 1) {
          context.lineTo(x(point), y(history[point].units));
        }
        context.lineTo(x(index - 1), bottom);
        context.closePath();
        context.fill();
      }
      runStart = index + 1;
    }

    function series(points, offset, hue, dash, previous) {
      context.lineWidth = 2.25;
      context.strokeStyle = hue;
      context.setLineDash(dash);
      context.lineCap = "round";
      context.lineJoin = "round";
      context.beginPath();
      let connected = previous?.units != null;
      if (connected) context.moveTo(x(offset - 1), y(previous.units));
      points.forEach((point, index) => {
        if (point.units === null) {
          connected = false;
          return;
        }
        const method = connected ? "lineTo" : "moveTo";
        context[method](x(index + offset), y(point.units));
        connected = true;
      });
      context.stroke();
      context.setLineDash([]);
      points.forEach((point, index) => {
        if (point.units === null) return;
        const cx = x(index + offset);
        const cy = y(point.units);
        context.fillStyle = point.stockout ? color("danger") : hue;
        context.beginPath();
        if (point.stockout) {
          context.moveTo(cx, cy - 4);
          context.lineTo(cx + 4, cy);
          context.lineTo(cx, cy + 4);
          context.lineTo(cx - 4, cy);
          context.closePath();
        } else {
          context.arc(cx, cy, index + offset === focusedPoint ? 4.5 : 2.2, 0, Math.PI * 2);
        }
        context.fill();
      });
    }

    series(history, 0, color("chart-actual"), []);
    series(prediction, history.length, color("chart-future"), [5, 4], history.at(-1));

    if (focusedPoint !== null) {
      context.strokeStyle = color("muted");
      context.lineWidth = 1;
      context.setLineDash([2, 5]);
      line(x(focusedPoint), top, x(focusedPoint), bottom);
      context.setLineDash([]);
    }
  }

  function line(x1, y1, x2, y2) {
    context.beginPath();
    context.moveTo(x1, y1);
    context.lineTo(x2, y2);
    context.stroke();
  }

  function hover(event) {
    if (!plot) return;
    const coordinate = event.clientX - canvas.getBoundingClientRect().left;
    const fraction = (coordinate - plot.left) / Math.max(1, plot.right - plot.left);
    const index = Math.min(data.length - 1, Math.max(0, Math.round(fraction * (data.length - 1))));
    if (focusedPoint === index) return;
    focusedPoint = index;
    const point = data[index];
    const label = index >= history.length ? "forecast" : "sold";
    const detail = point.units === null ? "no recorded sales" : point.units + " units " + label;
    tooltip.textContent = shortDate.format(new Date(point.day)) + " · " + detail + (point.stockout ? " · stockout" : "");
    tooltip.hidden = false;
    draw();
  }

  function dismiss() {
    if (focusedPoint === null) return;
    focusedPoint = null;
    tooltip.hidden = true;
    draw();
  }

  function onKey(event) {
    if (event.key === "Escape") dismiss();
  }

  const observer = new ResizeObserver(draw);
  observer.observe(canvas);
  canvas.addEventListener("pointermove", hover);
  canvas.addEventListener("pointerleave", dismiss);
  document.addEventListener("keydown", onKey);
  document.addEventListener("freshledger-theme-change", draw);
  return () => {
    observer.disconnect();
    canvas.removeEventListener("pointermove", hover);
    canvas.removeEventListener("pointerleave", dismiss);
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("freshledger-theme-change", draw);
    tooltip.hidden = true;
  };
}
