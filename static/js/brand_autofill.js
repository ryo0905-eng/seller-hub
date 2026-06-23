(function () {
    const dataElement = document.getElementById("brand-keywords-data");
    const titleInput = document.querySelector("[data-brand-title]");
    const brandInput = document.querySelector("[data-brand-input]");

    if (!dataElement || !titleInput || !brandInput) {
        return;
    }

    let brands = [];
    try {
        brands = JSON.parse(dataElement.textContent || "[]");
    } catch (error) {
        brands = [];
    }

    const normalize = (value) => value.trim().replace(/\s+/g, " ").toLowerCase();
    const sortedBrands = brands
        .map((brand) => String(brand || "").trim())
        .filter(Boolean)
        .sort((a, b) => b.length - a.length);

    let lastAutoBrand = "";

    const guessBrand = (title) => {
        const normalizedTitle = normalize(title);
        if (!normalizedTitle) {
            return "";
        }

        const matched = sortedBrands.find((brand) => normalizedTitle.startsWith(normalize(brand)));
        if (matched) {
            return matched;
        }

        return title.trim().split(/\s+/)[0] || "";
    };

    const autofillBrand = () => {
        const currentBrand = brandInput.value.trim();
        if (currentBrand && currentBrand !== lastAutoBrand) {
            return;
        }

        const nextBrand = guessBrand(titleInput.value);
        if (nextBrand === currentBrand) {
            return;
        }

        brandInput.value = nextBrand;
        lastAutoBrand = nextBrand;
        brandInput.dispatchEvent(new Event("input", { bubbles: true }));
    };

    titleInput.addEventListener("input", autofillBrand);
})();
