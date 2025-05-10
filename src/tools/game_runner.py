import json
from pydantic import BaseModel, Field
from typing import List, Optional, Union, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from fuzzywuzzy import process
import time
from langchain.tools import tool


# Основная модель для результата
class GameRequirementsResult(BaseModel):
    game: str
    cpu: str
    gpu: str
    ram: int
    requirements: Optional[str] = None
    fps_info: List[Any] 
    paragraphs: List[str] 
    error: Optional[str] = None


class InputData(BaseModel):
    game_name: Optional[str]
    cpu: Optional[str]
    gpu: Optional[str]
    ram: Optional[int] = None


def check_game_requirements(game_name, cpu, gpu, ram) -> Union[GameRequirementsResult, str]:
    """
    Проверка совместимости системных требований для игры.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 20)

    try:
        driver.get("https://technical.city/ru/can-i-run-it")

        game_name_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input.ui-autocomplete-input")))

        game_name_input.send_keys(game_name)

        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "ul.ui-menu.ui-widget.ui-widget-content.ui-autocomplete.highlight.ui-front")))

        game_item = wait.until(EC.element_to_be_clickable((By.XPATH, f"//span[@class='bold-text' and text()='{game_name}']")))

        game_item.click()

        cpu_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input.select-input[placeholder='Выберите процессор']")))
        cpu_input.send_keys(cpu)

        gpu_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input.select-input[placeholder='Выберите видеокарту']")))
        gpu_input.send_keys(gpu)
        gpu_list = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "ul.ui-menu.ui-widget.ui-widget-content.ui-autocomplete.highlight.ui-front li.ui-menu-item")))
        gpu_options = [gpu.text for gpu in gpu_list]
        best_match = process.extractOne(gpu, gpu_options)
        best_match_element = gpu_list[gpu_options.index(best_match[0])]
        best_match_element.click()

        ram_dropdown = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[@class='selecter-selected']")))
        ram_dropdown.click()
        ram_option = wait.until(EC.element_to_be_clickable((By.XPATH, f"//span[@class='selecter-item' and @data-value='{ram}']")))
        ram_option.click()

        time.sleep(2)

        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)

        requirements_notice = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//p[@class='notice']")))
        requirements_text = requirements_notice[0].text if requirements_notice else None

        paragraph_elements = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//p")))

        resolution_elements = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//div[@class='fps_quality_resolution']")))
        fps_elements = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//div[@class='fps_value']/em[@class='green' or @class='yellow' or @class='red']")))

        fps_data = []
        for i in range(min(len(resolution_elements), len(fps_elements))):
             fps_data.append({
            "resolution": resolution_elements[i].text.strip(),
            "fps": fps_elements[i].text.strip()
        })

        paragraphs = [paragraph_elements[i].text for i in [2, 5]]

        # Создаем результат и конвертируем в JSON
        result = GameRequirementsResult(
            game=game_name,
            cpu=cpu,
            gpu=best_match[0],
            ram=ram,
            requirements=requirements_text if requirements_text else "No requirements found",
            fps_info=fps_data,
            paragraphs=paragraphs
        )

        # Возвращаем результат в виде словаря, преобразуем в JSON
        return json.loads(result.json())  # Преобразуем результат в JSON

    except Exception as e:
        result = GameRequirementsResult(
            game=game_name,
            cpu=cpu,
            gpu=gpu,
            ram=ram,
            error=str(e)
        )
        return json.loads(result.model_dump_json())  # Преобразуем результат в JSON

    finally:
        driver.quit()


@tool
def game_run_tool(input_data: dict) -> dict:
    """
    Проверяет совместимость системных требований игры с заданными компонентами (процессор, видеокарта, оперативная память).
    Пример входных данных dict:
    
     "input_data": {
            "game_name": "Cyberpunk 207",
            "cpu": "Intel Core i7-12700",
            "gpu": "RTX 3070",
            "ram": 16,
        }
    """

    if "memory" in input_data:
        memory = input_data["memory"]
        input_data["ram"] = memory  
        del input_data["memory"]  

    try:
        validated_input = InputData.model_validate(input_data)
    except Exception as e:
        return {"error": f"Invalid input data: {str(e)}"}

    game_name = validated_input.game_name
    cpu = validated_input.cpu
    gpu = validated_input.gpu
    ram = validated_input.ram

    result = check_game_requirements(game_name, cpu, gpu, ram)

    return json.dumps(result, ensure_ascii=False, indent=4)


# if __name__ == "__main__":
#     input_parameter = {
#         "game_name": "Cyberpunk 2077",
#         "cpu": "Intel Core i7-12700",
#         "gpu": "RTX 3070",
#         "ram": 16
#     }

#     output = game_run_tool.invoke({"input_data": input_parameter})

#     print("\n📌 Результаты парсинга в формате JSON:")
#     print(output)  # Теперь выводим результат в формате JSON
