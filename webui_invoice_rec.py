import gradio as gr
from main import main as invoice_rec
import requests, cv2, json, os
from loguru import logger as log
from common.to_excel import to_excel


css = """
    #submit {
            margin: auto !important; 
            background: linear-gradient(to right, #ffe2c0, #fdc589); 
            color: #ea580c
            }
"""


def clear_image():
    return None, None, None


def image_to_excel(image_file):
    output_file = r'output/result.xlsx'
    for i in [output_file]:
        if os.path.exists(i):
            os.remove(i)
    log.info('图片上传成功！')
    log.info('调用发票识别...')
    try:
        result = invoice_rec(image_file)
    except Exception as e:
        log.warning('调用发票识别失败！')
        res = str(e)
        output_file = None
        return output_file, res

    res = json.dumps(result, indent = 4, ensure_ascii = False)

    excel_name = r'output/result.xlsx'
    to_excel(result, excel_name)
    log.info(f'导入Excel成功：{excel_name}')
    return output_file, res


def main():
    with gr.Blocks(title = "发票识别", css=css) as demo:
        with gr.Row():
            header = gr.Markdown("""
                        <div style="text-align: center; font-size: 25px; font-weight: bold;">
                        发票识别
                        </div>
                        """)
        with gr.Row():
            with gr.Column():
                upload_image = gr.Image(type='filepath', label = 'Upload Image')
                with gr.Row():
                    btn1 = gr.Button("清除")
                    btn2 = gr.Button("提交", elem_id="submit")
                with gr.Row():
                    examples = gr.Examples(examples = [r"test/1/1.jpg", r"test/1/2.jpg", r"test/1/3.jpg", r'test/1/4.png'],
                                           inputs = upload_image)

            with gr.Column():
                output_file = gr.File(label = "Download Excel")
                text = gr.Text(label='Json Response')

        btn1.click(clear_image, outputs = [upload_image, output_file, text])
        btn2.click(image_to_excel, inputs = upload_image, outputs = [output_file, text])

    demo.queue()
    demo.launch(server_name = "0.0.0.0", server_port = 8000, share = False, inbrowser = False)



if __name__ == "__main__":
    main()


