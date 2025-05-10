from typing import Dict, Optional, Any, List, Union
from pydantic import BaseModel, ValidationError, Field
from langchain.tools import tool
import json
import urllib.parse
import asyncio
from playwright.sync_api import sync_playwright
import time


class CPU(BaseModel):
    cpu: str = Field(..., description="Модель процессора", example="Intel Core i7-12700")


class GPU(BaseModel):
    gpu: str = Field(..., description="Модель видеокарты", example="GeForce RTX 3070")


class Memory(BaseModel):
    name: str = Field(..., description="Название памяти", example="Corsair Vengeance 16 GB")


class Corpus(BaseModel):
    name: str = Field(..., description="Модель корпуса", example="Cooler Master MasterBox")


class PowerSupply(BaseModel):
    name: str = Field(
        ..., description="Модель блока питания", example="Be Quiet! Pure Power 11 600W"
    )


class Motherboard(BaseModel):
    name: str = Field(..., description="Модель материнской платы", example="ASUS ROG Strix Z690-F")


Component = Union[CPU, GPU, Memory, Corpus, PowerSupply, Motherboard]


class ComponentInput(BaseModel):
    components: List[Component] = Field(
        ...,
        description="Список компонентов для анализа.",
        example=[{"cpu": "Intel Core i7-12700"}, {"gpu": "GeForce RTX 3070"}],
    )


class RegardInput(BaseModel):
    input_data: ComponentInput

    @classmethod
    def from_dict(cls, input_data: Dict[str, Any]) -> "RegardInput":
        """Метод преобразования словаря в объект `RegardInput`"""
        return cls(input_data=ComponentInput(**input_data))


def parse_first_product(page) -> Optional[Dict[str, Any]]:
    """Извлекает данные о первом товаре."""
    try:
        page.wait_for_selector(".CardText_link__C_fPZ", timeout=15000)

        name_element = page.query_selector(".CardText_title__7bSbO.CardText_listing__6mqXC")
        name = name_element.inner_text() if name_element else "Название не найдено"

        price_element = page.query_selector(".CardPrice_price__YFA2m .Price_price__m2aSe")
        price = (
            float(price_element.inner_text().replace("\xa0", "").replace("₽", "").strip())
            if price_element
            else "Цена не найдена"
        )

        link_element = page.query_selector(".CardText_link__C_fPZ")
        link = (
            "https://www.regard.ru" + (link_element.get_attribute("href")) if link_element else "#"
        )

        return {"name": name, "price": price, "link": link}
    except Exception as e:
        print(f"Ошибка парсинга товара: {str(e)}")
        return None


def apply_sorting(page, sort_text: str) -> Optional[Dict[str, Any]]:
    """Применяет сортировку и извлекает первый товар."""
    try:
        print(f"\nПрименяем сортировку: {sort_text}")

        sort_button = page.wait_for_selector(".SelectableList_wrap__uvkMK")
        sort_button.click()

        option = page.wait_for_selector(f"//span[text()='{sort_text}']")
        option.click()

        page.wait_for_selector(".CardText_link__C_fPZ")
        time.sleep(2)

        return parse_first_product(page)
    except Exception as e:
        print(f"Ошибка при сортировке: {str(e)}")
        return None


@tool(args_schema=RegardInput)
def regard_parser_tool(input_data: Dict) -> str:
    """Инструмент парсинга товаров с regard.ru."""
    # try:
    #     # ✅ Передаем данные в `ComponentInput`, затем в `RegardInput`
    #     print(input_data)
    #     data = RegardInput.from_dict(input_data)

    #     # Получаем список компонентов
    #     components = data.input_data.components
    #     print(f"Компоненты для анализа: {components}")
    components = input_data.components
    print(f"Компоненты для анализа: {components}")

    results = {}

    COMPONENT_CONFIG = {
        "cpu": lambda c: c.cpu,
        "gpu": lambda c: c.gpu,
        "memory": lambda c: c.name,
        "corpus": lambda c: c.name,
        "power_supply": lambda c: c.name,
        "motherboard": lambda c: c.name,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            for component in components:
                print(component)
                search_query = None
                for key, extractor in COMPONENT_CONFIG.items():
                    print(key)
                    if hasattr(component, key):
                        search_query = extractor(component)
                        print(f"🔍 Обработка компонента {key}: {search_query}")
                        break
                else:
                    print("Нет ключа")
                    continue

                encoded_query = urllib.parse.quote_plus(search_query)
                search_url = f"https://www.regard.ru/catalog?search={encoded_query}"
                print(f"Открываем страницу: {search_url}")
                page.goto(search_url, wait_until="domcontentloaded")

                sort_options = ["Сначала с низкой ценой", "Сначала дорогие", "Сначала популярные"]

                component_results = []
                for sort_type in sort_options:
                    try:
                        product_info = apply_sorting(page, sort_type)
                        if product_info:
                            component_results.append(
                                {
                                    "sort_type": sort_type,
                                    "name": product_info["name"],
                                    "price": product_info["price"],
                                    "link": product_info["link"],
                                }
                            )
                        time.sleep(2)
                    except Exception as e:
                        print(f"Ошибка при обработке {sort_type}: {str(e)}")
                        continue
                results[search_query] = component_results
        finally:
            browser.close()

    return json.dumps(results, ensure_ascii=False, indent=2)


def main():
    input_data = {"components": [{"cpu": "Intel Core i7-12700"}, {"gpu": "GeForce RTX 3070"}]}
    output = regard_parser_tool.invoke({"input_data": input_data})
    print(output)


if __name__ == "__main__":
    main()
