# type: ignore

from typing import Any

from langchain.tools import tool
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from thefuzz import process  # type: ignore


# Модели для входных и выходных данных
class InputParameters(BaseModel):
    cpu: str
    gpu: str
    resolution: str | None = "1080p"  # Если разрешение не указано, по умолчанию 1080p
    best_processor_match: str
    best_gpu_match: str


class PerformanceScenarios(BaseModel):
    gaming: str | None
    content_creation: str | None
    streaming: str | None


class Results(BaseModel):
    cpu_performance: str
    gpu_performance: str
    bottleneck_percentage: str
    performance_scenarios: PerformanceScenarios
    recommendations: list[str]


class BottleneckResponse(BaseModel):
    input_parameters: InputParameters
    results: Results


# Функция для расчета узкого горлышка между процессором и видеокартой
@tool
def calculate_bottleneck(input_json: dict[str, Any]) -> dict[str, Any]:
    """
    Расчет процента узкого горлышка операций между процессором и видеокартой при выбранном разрешении.

    Args:
        input_json (Dict[str, Any]): Входные данные в формате JSON, содержащие параметры для процессора, видеокарты и разрешения.
        input_json = {
        "cpu": "Ryzen 9 5950X",
        "gpu": "GeForce RTX 4070",
        "resolution": "1440p"
    }

    Returns:
        Dict[str, Any]: Результаты расчета в формате JSON.
    """
    # Загружаем входной JSON
    try:
        processor = input_json.get("cpu")
        gpu = input_json.get("gpu")
        resolution = input_json.get("resolution", "1080p")

        if not processor or not gpu:
            return {"error": "CPU and GPU must be provided"}

    except Exception as e:
        return {"error": str(e)}

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Запуск драйвера
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 20)
    driver.get("https://bottleneckcalculator.help/")

    try:
        # Функция для поиска наиболее похожего элемента из списка
        def get_best_match(input_text, elements_list):
            best_match = process.extractOne(input_text, elements_list)
            return best_match[0] if best_match else ""

        # 1. Заполнение поля для процессора
        processor_input = wait.until(ec.presence_of_element_located((By.ID, "processor")))

        processor_input.send_keys(processor)
        processor_list = [
            element.text
            for element in wait.until(
                ec.presence_of_all_elements_located((By.XPATH, "//div[@class='p-2']//span"))
            )
        ]
        processor_input.clear()
        processor_input.send_keys(get_best_match(processor, processor_list))

        # 2. Заполнение поля для GPU
        gpu_input = wait.until(ec.presence_of_element_located((By.ID, "graphics")))

        gpu_input.send_keys(gpu)
        gpu_list = [
            element.text
            for element in wait.until(
                ec.presence_of_all_elements_located((By.XPATH, "//div[@class='p-2']//span"))
            )
        ]
        gpu_input.clear()
        gpu_input.send_keys(get_best_match(gpu, gpu_list))

        try:
            calculate_button = wait.until(
                ec.element_to_be_clickable((By.XPATH, "//button[text()='Calculate Bottleneck']"))
            )
            driver.execute_script("arguments[0].scrollIntoView();", calculate_button)
            calculate_button.click()
        except Exception:
            driver.execute_script("arguments[0].click();", calculate_button)

        # Извлечение информации
        cpu_performance = wait.until(
            ec.presence_of_element_located(
                (By.XPATH, "//span[text()='CPU Performance']/following-sibling::span")
            )
        ).text
        gpu_performance = wait.until(
            ec.presence_of_element_located(
                (By.XPATH, "//span[text()='GPU Performance']/following-sibling::span")
            )
        ).text
        bottleneck_percentage = wait.until(
            ec.presence_of_element_located(
                (By.XPATH, "//h3[text()='Bottleneck Percentage']/following-sibling::p")
            )
        ).text

        # 4. Получение производительности в разных сценариях
        performance_scenarios = {
            scenario.find_element(By.XPATH, ".//h6")
            .text: scenario.find_element(By.XPATH, ".//p")
            .text
            for scenario in driver.find_elements(
                By.XPATH, "//div[contains(@class, 'flex flex-col items-center text-center')]"
            )
            if scenario.find_element(By.XPATH, ".//h6").text
            in ["Gaming", "Content Creation", "Streaming"]
        }

        # 5. Парсим екомендации
        recommendations = []

        # Собираем все возможные рекомендации
        performance_recommendations = driver.find_elements(
            By.XPATH, "//p[contains(text(), 'limiting')]"
        )
        recommendations.extend([rec.text for rec in performance_recommendations])
        other_recommendations = driver.find_elements(
            By.XPATH, "//ul[@class='list-disc list-inside space-y-2 text-gray-700 ml-0']//li"
        )
        recommendations.extend([rec.text for rec in other_recommendations])

        # Формирование ответа с использованием Pydantic
        input_params = InputParameters(
            cpu=processor,
            gpu=gpu,
            resolution=resolution,
            best_processor_match=get_best_match(processor, processor_list),
            best_gpu_match=get_best_match(gpu, gpu_list),
        )

        performance_scenarios_data = PerformanceScenarios(
            gaming=performance_scenarios.get("Gaming"),
            content_creation=performance_scenarios.get("Content Creation"),
            streaming=performance_scenarios.get("Streaming"),
        )

        results = Results(
            cpu_performance=cpu_performance,
            gpu_performance=gpu_performance,
            bottleneck_percentage=bottleneck_percentage,
            performance_scenarios=performance_scenarios_data,
            recommendations=recommendations,
        )

        bottleneck_response = BottleneckResponse(input_parameters=input_params, results=results)

        # Возвращаем результаты в формате JSON
        return bottleneck_response.model_dump()

    finally:
        # Закрытие браузера
        driver.quit()


# # Пример вызова функции
# if __name__ == "__main__":
#     input_json = {
#         "cpu": "Ryzen 9 5950X",
#         "gpu": "GeForce RTX 4070",
#         "resolution": "1440p"
#     }
#     result = calculate_bottleneck.ainvoke({'input_json':input_json})
#     print(result)
