import pdfplumber
import pandas as pd
import re

def parse_compilation_pdf(file_bytes, filename="PDF"):
    """
    Parser específico para o PDF "Análise dos Relatórios ENADE - 2014 a 2023"
    Extrai as tabelas de Participantes, Conceitos e Questionários.
    """
    records = []
    
    try:
        with pdfplumber.open(file_bytes) as pdf:
            current_indicator = None
            current_year = None
            
            for page in pdf.pages:
                text = page.extract_text() or ""
                
                # Detecta mudança de Indicador na página
                m_ind = re.search(r'INDICADOR\s+(\d+(?:\.\d+)?):?\s*(.*)', text)
                if m_ind:
                    ind_num = m_ind.group(1)
                    ind_name = m_ind.group(2).strip()
                    current_indicator = f"{ind_num} - {ind_name}"
                
                # Detecta ano na página
                m_ano = re.search(r'ENADE\s+(20\d{2})', text)
                if m_ano:
                    current_year = int(m_ano.group(1))
                    
                tables = page.extract_tables()
                if not tables:
                    continue
                    
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                        
                    clean_table = []
                    for row in table:
                        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                        clean_table.append(clean_row)
                        
                    header = [h.upper() for h in clean_table[0]]
                    header_str = " | ".join(header)
                    
                    # Indicador 1: Participantes
                    if "POPULAÇÃO" in header_str and "PRESENTES" in header_str:
                        idx_curso = 0
                        idx_pop = header.index("POPULAÇÃO")
                        idx_pres = header.index("PRESENTES")
                        
                        for row in clean_table[1:]:
                            if len(row) > max(idx_pop, idx_pres):
                                curso = row[idx_curso]
                                if not curso or "MACAPÁ" in curso.upper() or "IES" in curso.upper():
                                    continue
                                
                                pop = row[idx_pop]
                                pres = row[idx_pres]
                                
                                if pop.isdigit():
                                    records.append({
                                        "indicador": "1 - Participantes",
                                        "ano": current_year or 2023,
                                        "curso": curso,
                                        "sub_categoria": "População",
                                        "metrica": "Qtd",
                                        "valor": float(pop)
                                    })
                                if pres.isdigit():
                                    records.append({
                                        "indicador": "1 - Participantes",
                                        "ano": current_year or 2023,
                                        "curso": curso,
                                        "sub_categoria": "Presentes",
                                        "metrica": "Qtd",
                                        "valor": float(pres)
                                    })
                                    
                    # Indicador 2: Conceito
                    elif "CONCEITO ENADE" in header_str or "CONCEITO" in header_str:
                        idx_conc = -1
                        for i, h in enumerate(header):
                            if "CONCEITO" in h: idx_conc = i
                        
                        if idx_conc != -1:
                            for row in clean_table[1:]:
                                if len(row) > idx_conc:
                                    curso = row[0]
                                    if not curso or "MACAPÁ" in curso.upper() or "CÓDIGO" in curso.upper():
                                        continue
                                    conc = row[idx_conc]
                                    if conc.isdigit():
                                        records.append({
                                            "indicador": "2 - Conceito ENADE",
                                            "ano": current_year or 2023,
                                            "curso": curso,
                                            "sub_categoria": None,
                                            "metrica": "Nota",
                                            "valor": float(conc)
                                        })
                                        
                    # Indicadores Questionário (7.x, etc)
                    elif "CURSO" in header_str and ("REGIÃO" in header_str or "BRASIL" in header_str):
                        # Pega o texto da tabela para saber o curso (algumas tabelas têm o curso no título)
                        # O PDF compilado agrupa por indicador e lista os cursos
                        idx_curso = -1
                        idx_brasil = -1
                        idx_ies = -1
                        
                        for i, h in enumerate(header):
                            if "CURSO" in h or "ÁREA" in h: idx_curso = i
                            if "BRASIL" in h: idx_brasil = i
                            if "IES" in h or "CURSO" in h: idx_ies = i # No compêndio, a IES é a própria nota
                            
                        # Se tem coluna "Curso", pode ser que as linhas sejam os cursos
                        for row in clean_table[1:]:
                            if len(row) < 3: continue
                            curso_nome = row[0]
                            if not curso_nome or "MACAPÁ" in curso_nome: continue
                            
                            # Tenta pegar valor IES e Brasil
                            val_ies = row[1].replace(',', '.') if len(row) > 1 else ""
                            val_br = row[-1].replace(',', '.') if len(row) > 2 else ""
                            
                            try:
                                if val_ies and val_ies != "-":
                                    records.append({
                                        "indicador": current_indicator or "Questionário",
                                        "ano": current_year or 2023,
                                        "curso": curso_nome,
                                        "sub_categoria": "IES",
                                        "metrica": "Percentual",
                                        "valor": float(val_ies)
                                    })
                                if val_br and val_br != "-":
                                    records.append({
                                        "indicador": current_indicator or "Questionário",
                                        "ano": current_year or 2023,
                                        "curso": curso_nome,
                                        "sub_categoria": "Brasil",
                                        "metrica": "Percentual",
                                        "valor": float(val_br)
                                    })
                            except ValueError:
                                pass

    except Exception as e:
        import traceback
        print(f"Erro em parse_compilation_pdf: {traceback.format_exc()}")
        raise e
        
    return records
