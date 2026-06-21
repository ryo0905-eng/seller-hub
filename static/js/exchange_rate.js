(function () {
    const helpers = Array.from(document.querySelectorAll("[data-exchange-rate-url]"));
    if (!helpers.length) {
        return;
    }

    const url = helpers[0].dataset.exchangeRateUrl;

    const setError = function () {
        helpers.forEach(function (helper) {
            const valueEl = helper.querySelector("[data-role='exchange-rate-value']");
            const metaEl = helper.querySelector("[data-role='exchange-rate-meta']");

            valueEl.textContent = "取得できません";
            metaEl.textContent = "手入力してください";
            helper.classList.add("is-error");
        });
    };

    fetch(url, {
        headers: {
            "Accept": "application/json",
        },
    })
        .then(function (response) {
            if (!response.ok) {
                throw new Error("exchange rate request failed");
            }
            return response.json();
        })
        .then(function (data) {
            if (!data.ok || !data.rate) {
                throw new Error("exchange rate payload invalid");
            }

            helpers.forEach(function (helper) {
                const valueEl = helper.querySelector("[data-role='exchange-rate-value']");
                const metaEl = helper.querySelector("[data-role='exchange-rate-meta']");
                const applyButton = helper.querySelector("[data-role='apply-exchange-rate']");
                const targetInput = document.getElementById(helper.dataset.targetInputId);

                valueEl.textContent = "1 USD = " + data.rate + " JPY";
                metaEl.textContent = [data.provider, data.date].filter(Boolean).join(" / ");
                applyButton.disabled = false;
                applyButton.addEventListener("click", function () {
                    if (targetInput) {
                        targetInput.value = data.rate;
                        targetInput.dispatchEvent(new Event("input", { bubbles: true }));
                        targetInput.focus();
                    }
                });
            });
        })
        .catch(setError);
})();
