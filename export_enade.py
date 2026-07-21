import pandas as pd
import io
import re

def inferir_tipo_curso(nome_curso):
    nome_curso_upper = nome_curso.upper()
    if "FILOSOFIA" in nome_curso_upper or "LETRAS" in nome_curso_upper or "PEDAGOGIA" in nome_curso_upper or "MÚSICA" in nome_curso_upper or "MUSICA" in nome_curso_upper or "QUIMICA" in nome_curso_upper or "QUÍMICA" in nome_curso_upper:
        if "ENGENHARIA" in nome_curso_upper:
            return "Bacharelado"
        return "Licenciatura"
    return "Bacharelado"

def gerar_excel_enade(df_enade):
    output = io.BytesIO()
    
    writer = pd.ExcelWriter(output, engine='xlsxwriter', engine_kwargs={'options': {'nan_inf_to_errors': True}})
    workbook = writer.book
    worksheet = workbook.add_worksheet('ENADE Dados')
    writer.sheets['ENADE Dados'] = worksheet
    
    row_idx = 0
    
    # Sort indicators, but let's keep the order of numbers
    def extrair_num(ind):
        m = re.match(r'^(\d+)', str(ind))
        return int(m.group(1)) if m else 999
        
    indicadores = sorted(df_enade['indicador'].dropna().unique(), key=extrair_num)
    
    for indicador in indicadores:
        df_ind = df_enade[df_enade['indicador'] == indicador]
        
        num_indicador = ""
        m = re.match(r'^(\d+)', str(indicador))
        if m:
            num_indicador = m.group(1)
            
        worksheet.write(row_idx, 0, "Número Indicador")
        worksheet.write(row_idx, 1, num_indicador)
        row_idx += 1
        
        worksheet.write(row_idx, 0, "Indicador")
        nome_ind = str(indicador).split('-')[-1].strip() if '-' in str(indicador) else str(indicador)
        
        # O indicador 5 tem uma pergunta hardcoded no pdf
        pergunta = ""
        if "5" in str(num_indicador):
            pergunta = "Ao longo da sua trajetória acadêmica, você recebeu algum tipo de auxilío permanência?"
        elif "6" in str(num_indicador):
            pergunta = "Ao longo da sua trajetória acadêmica, você recebeu algum tipo de bolsa acadêmica?"
            
        worksheet.write(row_idx, 1, nome_ind)
        row_idx += 1
        
        anos = df_ind['ano'].unique()
        for ano in sorted(anos):
            df_ano = df_ind[df_ind['ano'] == ano]
            
            worksheet.write(row_idx, 0, "Ano")
            worksheet.write(row_idx, 1, ano)
            if "Conceito Enade" in nome_ind or "7" in str(num_indicador) and ano == 2014:
                # O PDF mostra "Ano 2014 Conceito Enade" na mesma linha
                pass # Apenas visual no PDF, podemos deixar separado
            row_idx += 1
            
            tem_sub = df_ano['sub_categoria'].notna().any() and (df_ano['sub_categoria'] != "Percentual Concordância").all()
            
            if tem_sub:
                if pergunta:
                    worksheet.write(row_idx, 0, "Pergunta:")
                    worksheet.write(row_idx, 1, pergunta)
                    row_idx += 1
                
                cursos = df_ano['curso'].dropna().unique()
                for curso in sorted(cursos):
                    df_curso = df_ano[df_ano['curso'] == curso]
                    
                    worksheet.write(row_idx, 0, "Curso")
                    worksheet.write(row_idx, 1, curso)
                    row_idx += 1
                    
                    metricas = [m for m in df_curso['metrica'].unique() if pd.notna(m)]
                    worksheet.write(row_idx, 0, "Resposta")
                    worksheet.write(row_idx, 1, "Curso" if "Curso" in metricas else metricas[0] if len(metricas)>0 else "")
                    
                    col_idx = 2
                    metricas_resto = [m for m in metricas if m != "Curso"]
                    for m in metricas_resto:
                        worksheet.write(row_idx, col_idx, m)
                        col_idx += 1
                    row_idx += 1
                    
                    respostas = df_curso['sub_categoria'].dropna().unique()
                    respostas_str = sorted([str(r) for r in respostas])
                    for resp in respostas_str:
                        df_resp = df_curso[df_curso['sub_categoria'] == resp]
                        worksheet.write(row_idx, 0, resp)
                        
                        # Escreve a métrica "Curso" ou a primeira
                        if "Curso" in metricas:
                            val = df_resp[df_resp['metrica'] == "Curso"]['valor']
                            if not val.empty: worksheet.write(row_idx, 1, val.values[0])
                        
                        c_idx = 2
                        for m in metricas_resto:
                            val = df_resp[df_resp['metrica'] == m]['valor']
                            if not val.empty: worksheet.write(row_idx, c_idx, val.values[0])
                            c_idx += 1
                        row_idx += 1
                    row_idx += 1
            else:
                worksheet.write(row_idx, 0, "cidade")
                worksheet.write(row_idx, 1, "Macapá")
                row_idx += 1
                
                metricas = [m for m in df_ano['metrica'].unique() if pd.notna(m)]
                worksheet.write(row_idx, 0, "curso:")
                worksheet.write(row_idx, 1, "Tipo")
                
                col_idx = 2
                for m in metricas:
                    worksheet.write(row_idx, col_idx, m)
                    col_idx += 1
                row_idx += 1
                
                cursos = df_ano['curso'].dropna().unique()
                for curso in sorted(cursos):
                    df_curso = df_ano[df_ano['curso'] == curso]
                    worksheet.write(row_idx, 0, curso)
                    worksheet.write(row_idx, 1, inferir_tipo_curso(curso))
                    
                    c_idx = 2
                    for m in metricas:
                        val = df_curso[df_curso['metrica'] == m]['valor']
                        if not val.empty: worksheet.write(row_idx, c_idx, val.values[0])
                        c_idx += 1
                    row_idx += 1
                row_idx += 1
                
        row_idx += 1
        
    writer.close()
    return output.getvalue()
