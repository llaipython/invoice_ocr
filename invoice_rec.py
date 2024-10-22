import cv2
import re
from datetime import datetime
import numpy as np

from common.json_parse import jsonfile_to_dict
from common.params import args
from common.regular_matching import Regular_match
from ocr_system_base import OCR, text_sys
from common.contour_detection import contour_detection
from common.ocr_utils import re_map, fourxy2twoxy
from template.structured_common import structured, re_map_template
import copy
from loguru import logger as log


class InvoiceRec():
    def __init__(self, img):
        self.img = img

    def invoice_warp(self):
        '''
        根据轮廓四点坐标进行透视变换
        Returns:

        '''
        img = self.img
        b, g, r = list(map(int, cv2.meanStdDev(img)[0].squeeze()))
        borderValue = (b, g, r)

        corner_point = contour_detection(self.img)
        if corner_point is not None:
            p2 = np.array([(100, 250), (1800, 250), (1800, 1050), (100, 1050)], dtype = np.float32)
            M = cv2.getPerspectiveTransform(corner_point, p2)
            new_img = cv2.warpPerspective(img, M, (1900, 1200), borderValue = borderValue)
            self.warp = True
        else:
            new_img = img
            self.warp = False
        if args.is_visualize:
            cv2.imwrite(r'test/adjust.jpg', new_img)
        return new_img

    def ocr(self, new_img):
        '''
        使用透视变换后的图片进行ocr文件检测+文本识别模型
        '''
        ocr = OCR(text_sys, new_img)
        return ocr



    def make_template(self, new_img, ocr):
        json_info = ocr(union=False)
        json_info_union = ocr(union = True, max_x_dist = 50, min_y_overlap_ratio = 0.5)
        bbox_maxh = 0
        for index, dic in enumerate(json_info_union[:6]):
            bbox = dic['origin_box'][0]
            h = bbox[5] - bbox[3]
            if h > bbox_maxh and len(dic["text"]) > 3:
                bbox_maxh = h
                bbox_maxh_index = index

        flag_electric = False
        flag_quandian = False
        index_daima = 0
        flag_daima = False
        # flag_check_code = False
        for index, dic in enumerate(json_info[:6]):
            # re_result = re_map(['机器编号', '电子', '机器', '电动', '电[子]?'], dic['text'])
            re_result = re_map(['电子.*发票', '发票代码', '发票号码', '电子', '电.*发票'], dic['text'])
            re_result_daima = re_map(['发票代码', '代码'], dic['text'])
            re_result_check_code = re_map(['校[\s]?验[\s]?码[\s]'], dic['text'])
            if re_result:
                flag_electric = True
            if re_result_daima:
                index_daima = index
                flag_daima = True
            # if re_result_check_code:
            #     flag_check_code = True
        if flag_electric and not flag_daima:
            flag_quandian = True

        def function(flag_quandian):
            if flag_quandian:
                from template.structured_quandian import re_dict
                labelme_file = r'template_quandian.json'
            else:
                pos = json_info_union[bbox_maxh_index]['origin_box'][0][3]  # 发票抬头
                if pos - json_info[index_daima]['box'][1] > 12:
                    labelme_file = r'template_electronic_v1.json'
                else:
                    labelme_file = r'template_electronic_v2.json'
                from template.structured_electronic import re_dict

            rectangle_dict, drop_ind, key_ind, detail_dict, re_dict = structured(re_dict,
                                                                                 labelme_file = labelme_file)
            return rectangle_dict, drop_ind, key_ind, detail_dict, re_dict

        if flag_electric:
            rectangle_dict, drop_ind, key_ind, detail_dict, re_dict = function(flag_quandian)
        else:
            from template.structured_paper import re_dict
            rectangle_dict, drop_ind, key_ind, detail_dict, re_dict = structured(re_dict,
                                                                                 labelme_file = r'template_paper.json')


        drop_ind += [0]
        tmp = np.zeros((1200, 1900), dtype = 'uint8')
        for r in rectangle_dict:
            cv2.rectangle(tmp, tuple(rectangle_dict[r][0]), tuple(rectangle_dict[r][1]), r, thickness = cv2.FILLED)

        if args.is_visualize:
            anchor_img = copy.deepcopy(new_img)
            for r in rectangle_dict:
                cv2.rectangle(anchor_img, tuple(rectangle_dict[r][0]), tuple(rectangle_dict[r][1]), 255,
                              thickness = 2)
            cv2.imwrite('./test/draw_anchor_box.jpg', anchor_img)


        detail_dict, key_ind = copy.deepcopy(detail_dict), copy.deepcopy(key_ind)
        for key in key_ind:
            key_ind[key][2] = rectangle_dict[key]  # todo

        for t in json_info:
            point = [int(t["bbox"][0] + t["bbox"][2]) // 2, int(t["bbox"][1] + t["bbox"][3]) // 2]
            text = t["text"]
            try:
                label_ind = tmp[point[1]][point[0]]
            except:
                log.warning(f'index {label_ind} is out of bounds')
            if label_ind in drop_ind:
                continue
            elif label_ind in detail_dict:
                detail_dict[label_ind].append([text, point])
                continue
            else:
                key_ind[label_ind][1] += text

        return re_dict, key_ind, detail_dict

    def get_result(self, re_dict, key_ind, detail_dict, new_img):
        flag_code_res, invoice_type, invoice_daima, invoice_haoma, total_money, date, check_code = self.code_res(new_img)
        coderes = {"发票抬头": invoice_type, "发票代码": invoice_daima, "发票号码": invoice_haoma,
                   "开票日期": date, "合计金额": total_money, '校验码': check_code}
        res = []
        for k in copy.deepcopy(key_ind):
            if k == 53:
                text_res = re_map_template(re_dict[k], key_ind[k][1], title = True)
                if flag_code_res:
                    if invoice_type != "": text_res = invoice_type
            else:
                text_res = re_map_template(re_dict[k], key_ind[k][1], title = False)
                if flag_code_res:
                    if key_ind[k][0] in ['发票代码', '发票号码', '校验码'] and coderes[key_ind[k][0]] != '':
                        text_res = coderes[key_ind[k][0]]
            res.append({"key": key_ind[k][0], "value": text_res})

        result = {}
        for dic in res:
            result[dic['key']] = dic['value']

        detail_names = ["货物或应税劳务、服务名称", "规格型号", "单位", "数量", "单价", "金额", "税率", "税额"]
        detail_values = ['', '', '', '', '', '', '', '']
        for index, d in enumerate(detail_dict.values()):
            value = [i[0] for i in d]
            value = ''.join(value)
            detail_values[index] = value

        detail_result = dict(zip(detail_names, detail_values))

        result.update(detail_result)
        return result

    def filter_result(self, result, key_list):
        if key_list == []:
            return result

        finally_result = dict(zip(key_list, [""]*len(key_list)))
        for k, v in result.items():
            if k in key_list:
                finally_result[k] = v
        return finally_result

    def __call__(self, key_list=[]):
        new_img = self.invoice_warp()
        ocr = self.ocr(new_img)
        if self.warp:
            re_dict, key_ind, detail_dict = self.make_template(new_img, ocr)
            result = self.get_result(re_dict, key_ind, detail_dict, new_img)
        else:
            log.warning('轮廓检测失败')
            json_path = r'template/config.json'
            regulation_key = jsonfile_to_dict(json_path = json_path)
            rm = Regular_match(ocr, None, regulation_key, shape = new_img.shape)
            result = rm()

        finally_result = self.filter_result(result, key_list = key_list)
        return finally_result




