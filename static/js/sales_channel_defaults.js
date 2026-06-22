(function () {
    const channelInput = document.querySelector("[data-sales-channel]");
    const feeInput = document.querySelector("[data-platform-fee-rate]");
    const rateInput = document.querySelector("[data-sale-price-exchange-rate]");

    if (!channelInput) {
        return;
    }

    const applyDefaults = function () {
        if (channelInput.value === "mercari") {
            if (feeInput && (!feeInput.value || feeInput.value === "15.00")) {
                feeInput.value = "10.00";
            }
            if (rateInput && !rateInput.value) {
                rateInput.value = "1.00";
            }
        }

        if (channelInput.value === "ebay" && feeInput && (!feeInput.value || feeInput.value === "10.00")) {
            feeInput.value = "15.00";
        }
    };

    channelInput.addEventListener("change", applyDefaults);
})();
