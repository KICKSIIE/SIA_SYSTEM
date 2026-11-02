// Only adds and removes rows in the item tables of the forms. No business logic here.
document.addEventListener("click", function (e) {
  var add = e.target.closest("[data-add-row]");
  if (add) {
    var tbody = document.querySelector("#" + add.dataset.addRow + " tbody");
    var row = tbody.querySelector(".line-row").cloneNode(true);
    row.querySelectorAll("input").forEach(function (i) { if (i.type !== "checkbox") { i.value = ""; } });
    row.querySelectorAll("select").forEach(function (s) { s.selectedIndex = 0; });
    tbody.appendChild(row);
  }
  var rem = e.target.closest("[data-remove-row]");
  if (rem) {
    var tb = rem.closest("tbody");
    if (tb.querySelectorAll(".line-row").length > 1) { rem.closest("tr").remove(); }
  }
});

// Display helpers for the item tables (no business rules here, the server checks everything).
document.addEventListener("change", function (e) {
  var sel = e.target.closest("select[data-fill-onhand]");
  if (sel) {
    var row = sel.closest("tr"), opt = sel.options[sel.selectedIndex];
    var shown = row.querySelector("input[name='on_hand[]'], input[name='qty_system[]']");
    if (shown) { shown.value = opt && opt.dataset.onhand !== undefined ? opt.dataset.onhand : ""; }
    updateDiff(row);
  }
});
document.addEventListener("input", function (e) {
  if (e.target.matches("[data-diff]")) { updateDiff(e.target.closest("tr")); }
});
function updateDiff(row) {
  var sys = row.querySelector("input[name='qty_system[]']"), act = row.querySelector("input[data-diff]"),
      diff = row.querySelector("input[name='qty_diff[]']");
  if (sys && act && diff) { diff.value = (sys.value !== "" && act.value !== "") ? (Number(act.value) - Number(sys.value)) : ""; }
}
