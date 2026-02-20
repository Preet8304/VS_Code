(function () {
  const form = document.getElementById("invoiceForm");
  if (!form) return;

  const tbody = document.querySelector("#itemsTable tbody");
  const addItemBtn = document.getElementById("addItemBtn");
  const itemsJsonInput = document.getElementById("items_json");
  const subtotalEl = document.getElementById("subtotal");
  const gstEl = document.getElementById("gst_total");
  const grandEl = document.getElementById("grand_total");

  const chargeInputs = ["loading_charge", "transport_charge", "discount"].map((id) =>
    document.getElementById(id)
  );

  function makeProductOptions() {
    return window.PRODUCTS.map(
      (p) => `<option value="${p.id}">${p.name} | Stock: ${p.stock}</option>`
    ).join("");
  }

  function rowTemplate() {
    return `
      <tr>
        <td><select class="product_id">${makeProductOptions()}</select></td>
        <td><input class="qty" type="number" step="0.01" value="1"></td>
        <td><input class="rate" type="number" step="0.01" value="0"></td>
        <td><input class="gst" type="number" step="0.01" value="0"></td>
        <td class="line_total">0.00</td>
        <td><button type="button" class="remove">X</button></td>
      </tr>
    `;
  }

  function getProductById(productId) {
    return window.PRODUCTS.find((p) => String(p.id) === String(productId));
  }

  function hydrateRow(row) {
    const select = row.querySelector(".product_id");
    const rate = row.querySelector(".rate");
    const gst = row.querySelector(".gst");
    const p = getProductById(select.value);
    if (!p) return;
    rate.value = p.rate;
    gst.value = p.gst_percent;
  }

  function recalculate() {
    let subtotal = 0;
    let gstTotal = 0;
    const items = [];

    tbody.querySelectorAll("tr").forEach((row) => {
      const productId = row.querySelector(".product_id").value;
      const qty = Number(row.querySelector(".qty").value || 0);
      const rate = Number(row.querySelector(".rate").value || 0);
      const gstPercent = Number(row.querySelector(".gst").value || 0);

      const taxable = qty * rate;
      const gstAmount = (taxable * gstPercent) / 100;
      const lineTotal = taxable + gstAmount;

      subtotal += taxable;
      gstTotal += gstAmount;
      row.querySelector(".line_total").textContent = lineTotal.toFixed(2);

      items.push({
        product_id: Number(productId),
        qty,
        rate,
        gst_percent: gstPercent,
      });
    });

    const loading = Number(document.getElementById("loading_charge").value || 0);
    const transport = Number(document.getElementById("transport_charge").value || 0);
    const discount = Number(document.getElementById("discount").value || 0);
    const grand = subtotal + gstTotal + loading + transport - discount;

    subtotalEl.textContent = subtotal.toFixed(2);
    gstEl.textContent = gstTotal.toFixed(2);
    grandEl.textContent = grand.toFixed(2);
    itemsJsonInput.value = JSON.stringify(items);
  }

  function addRow() {
    tbody.insertAdjacentHTML("beforeend", rowTemplate());
    const row = tbody.lastElementChild;
    hydrateRow(row);
    recalculate();
  }

  addItemBtn.addEventListener("click", addRow);
  tbody.addEventListener("change", (e) => {
    const target = e.target;
    if (target.classList.contains("product_id")) {
      hydrateRow(target.closest("tr"));
    }
    recalculate();
  });
  tbody.addEventListener("input", recalculate);
  tbody.addEventListener("click", (e) => {
    const target = e.target;
    if (!target.classList.contains("remove")) return;
    target.closest("tr").remove();
    recalculate();
  });
  chargeInputs.forEach((el) => el.addEventListener("input", recalculate));
  form.addEventListener("submit", recalculate);

  addRow();
})();
