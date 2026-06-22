(function () {
    const usdInput = document.querySelector("[data-sale-price-usd]");
    const jpyInput = document.querySelector("[data-sale-price-jpy]");
    const rateInput = document.querySelector("[data-sale-price-exchange-rate]");

    if (!usdInput || !jpyInput || !rateInput) {
        return;
    }

    let lastEdited = usdInput.value ? "usd" : "jpy";

    const parseNumber = function (value) {
        const parsed = Number(String(value || "").replace(/,/g, ""));
        return Number.isFinite(parsed) ? parsed : null;
    };

    const setJpyFromUsd = function () {
        const usd = parseNumber(usdInput.value);
        const rate = parseNumber(rateInput.value);
        if (usd === null || rate === null || usd <= 0 || rate <= 0) {
            return;
        }
        jpyInput.value = Math.round(usd * rate);
    };

    const setUsdFromJpy = function () {
        const jpy = parseNumber(jpyInput.value);
        const rate = parseNumber(rateInput.value);
        if (jpy === null || rate === null || jpy <= 0 || rate <= 0) {
            return;
        }
        usdInput.value = (jpy / rate).toFixed(2);
    };

    usdInput.addEventListener("input", function () {
        lastEdited = "usd";
        setJpyFromUsd();
    });

    jpyInput.addEventListener("input", function () {
        lastEdited = "jpy";
        setUsdFromJpy();
    });

    rateInput.addEventListener("input", function () {
        if (lastEdited === "jpy") {
            setUsdFromJpy();
        } else {
            setJpyFromUsd();
        }
    });
})();
