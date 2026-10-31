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
