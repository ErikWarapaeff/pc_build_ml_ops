import json
import time
from typing import List, Optional
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from pydantic import BaseModel
from langchain.tools import tool


class ComponentInput(BaseModel):
    type: str
    name: str


class ComponentOutput(BaseModel):
    type: str
    name: str
    price: int
    url: str


class ExtremeProductsOutput(BaseModel):
    type: str
    cheapest: Optional[ComponentOutput]
    most_expensive: Optional[ComponentOutput]


class Product(BaseModel):
    url: str
    name: str
    price: int


# ------------------- Функции -------------------
def generate_url(component_type: str, name: str, page: int) -> str:
    """Генерирует URL для заданного типа компонента."""
    base_urls = {
        "cpu": "https://www.dns-shop.ru/catalog/17a899cd16404e77/processory/?q={name}&p={page}",
        "gpu": "https://www.dns-shop.ru/catalog/17a89aab16404e77/videokarty/?q={name}&p={page}",
        "memory": "https://www.dns-shop.ru/catalog/17a89a3916404e77/operativnaya-pamyat-dimm/?q={name}&p={page}",
        "cpu-cooler": "https://www.dns-shop.ru/catalog/17a9cc2d16404e77/kulery-dlya-processorov/?q={name}&p={page}",
        "case": "https://www.dns-shop.ru/catalog/17a8a01d16404e77/korpusa/?q={name}&p={page}",
        "motherboard": "https://www.dns-shop.ru/catalog/17a89a0416404e77/materinskie-platy/?q={name}&p={page}",
        "power-supply": "https://www.dns-shop.ru/catalog/17a89c2216404e77/bloki-pitaniya/?q={name}&p={page}",
    }
    if component_type not in base_urls:
        raise ValueError(f"Неизвестный компонент: {component_type}")

    return base_urls[component_type].format(name=name.replace(" ", "+"), page=page)


def get_products_from_page(page) -> List[Product]:
    """Собирает все товары на текущей странице."""
    try:
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        elements = soup.find_all("a", class_="catalog-product__name ui-link ui-link_black")
        if not elements:
            print("⚠️ Товары не найдены на странице!")
            return []

        names = [element.text.strip() for element in elements]

        price_elements = soup.find_all("div", class_="product-buy__price")
        prices = []
        for price in price_elements:
            try:
                prices.append(int(price.text.strip().replace(" ", "")[:-3]))
            except ValueError:
                prices.append(None)

        urls = [
            "https://www.dns-shop.ru" + element.get("href") + "characteristics/"
            for element in elements
        ]

        return [
            Product(url=url, name=name, price=price)
            for url, name, price in zip(urls, names, prices)
            if price
        ]

    except Exception as e:
        print(f"❌ Ошибка при парсинге страницы: {e}")
        return []


def get_all_products(
    playwright, component: ComponentInput, user_agent: str
) -> List[ComponentOutput]:
    """Получает все товары из категории с указанным User-Agent."""
    browser = playwright.chromium.launch(headless=False, slow_mo=100)
    context = browser.new_context(user_agent=user_agent)
    page = context.new_page()

    products = []
    page_number = 1

    while True:
        url = generate_url(component.type, component.name, page_number)
        print(f"🔎 Открываем страницу: {url}")

        page.goto(url, timeout=60000)

        try:
            page.wait_for_selector(".catalog-product__name", timeout=20000)
        except Exception as e:
            print(f"⚠️ Проблема с загрузкой страницы: {e}")
            break

        time.sleep(2)

        page.pause()

        page_products = get_products_from_page(page)
        if not page_products:
            break

        products.extend(page_products)
        page_number += 1

    browser.close()

    return [
        ComponentOutput(
            type=component.type, name=product.name, price=product.price, url=product.url
        )
        for product in products
    ]


def find_extreme_products(products: List[ComponentOutput]) -> ExtremeProductsOutput:
    """Находит самый дешевый и самый дорогой товар."""
    if not products:
        return ExtremeProductsOutput(type="", cheapest=None, most_expensive=None)

    cheapest = min(products, key=lambda x: x.price, default=None)
    most_expensive = max(products, key=lambda x: x.price, default=None)

    return ExtremeProductsOutput(
        type=products[0].type if products else "", cheapest=cheapest, most_expensive=most_expensive
    )


# ------------------- Инструмент-парсер DNS -------------------
@tool
def dns_parser_tool(input_json: str) -> str:
    """
    📌 Инструмент парсинга DNS.

    **Формат входного JSON:**
    ```json
    {
        "components": [
            {"type": "cpu", "name": "AMD Ryzen 9 7950X3D"},
            {"type": "gpu", "name": "Geforce RTX 4080 SUPER"}
        ]
    }
    ```

    **Выходные данные:** JSON с самыми дешевыми и дорогими товарами.
    """
    try:
        data = json.loads(input_json)
        components_data = data.get("components", [])
        components = [ComponentInput(**item) for item in components_data]
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)

    results = []
    # Пример User-Agent для Mozilla Firefox
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0"

    with sync_playwright() as playwright:
        for component in components:
            print(f"Обработка: {component.type} - {component.name}")
            try:
                products = get_all_products(playwright, component, user_agent)
                extreme_products = find_extreme_products(products)
                results.append(extreme_products.model_dump())

                if extreme_products.cheapest:
                    print(
                        f"{component.type}: Самый дешевый: {extreme_products.cheapest.name} - {extreme_products.cheapest.price} ₽"
                    )
                if extreme_products.most_expensive:
                    print(
                        f"Самый дорогой: {extreme_products.most_expensive.name} - {extreme_products.most_expensive.price} ₽"
                    )

            except Exception as e:
                print(f"Ошибка для {component.type}: {e}")

    return json.dumps(results, ensure_ascii=False, indent=2)


# ------------------- Пример использования -------------------
# if __name__ == '__main__':
#     sample_request = {
#         "components": [
#             {"type": "cpu", "name": "AMD Ryzen 9 7950X3D"},
#             {"type": "gpu", "name": "Geforce RTX 4080 SUPER"},
#             {"type": "motherboard", "name": "MSI MAG B660M MORTAR WIFI"}
#         ]
#     }
#     input_json = json.dumps(sample_request, ensure_ascii=False)
#     output = dns_parser_tool(input_json)

#     print("\n📌 Результаты парсинга:")
#     print(output)
