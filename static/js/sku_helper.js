(function () {
    const skuInput = document.querySelector("[data-sku-input]");
    const dateInput = document.querySelector("[data-sku-date]");

    if (!skuInput || !dateInput) {
        return;
    }

    let lastAutoSku = skuInput.value.trim();

    const sequenceFromSku = function (sku) {
        const match = String(sku || "").match(/-(\d+)$/);
        return match ? match[1] : "001";
    };

    const datePrefix = function (value) {
        const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
        return match ? match[1] + match[2] + match[3] : "";
    };

    const updateSkuFromDate = function () {
        const currentSku = skuInput.value.trim();
        if (currentSku && currentSku !== lastAutoSku) {
            return;
        }

        const prefix = datePrefix(dateInput.value);
        if (!prefix) {
            return;
        }

        const nextSku = prefix + "-" + sequenceFromSku(lastAutoSku || currentSku);
        skuInput.value = nextSku;
        lastAutoSku = nextSku;
        skuInput.dispatchEvent(new Event("input", { bubbles: true }));
    };

    skuInput.addEventListener("input", function () {
        if (skuInput.value.trim() !== lastAutoSku) {
            lastAutoSku = "";
        }
    });

    dateInput.addEventListener("input", updateSkuFromDate);
})();
