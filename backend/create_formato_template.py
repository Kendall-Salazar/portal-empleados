"""
One-time script to create formato_template.xlsm with VBA macro.
The VBA macro auto-propagates fill color changes from the FORMATO column
to the employee's name cells in both the Horario and Obligaciones tables.

Usage: python create_formato_template.py
Requires: pywin32, Microsoft Excel installed.
Note: You may need to enable "Trust access to the VBA project object model"
      in Excel: File > Options > Trust Center > Trust Center Settings > 
      Macro Settings > Check the box.
"""

import win32com.client
import os
import sys
import time

VBA_CODE = r'''
Private Sub Worksheet_SelectionChange(ByVal Target As Range)
    ' Auto-propagate FORMATO column fill AND font colors to ENTIRE ROWS in both tables
    ' Fires on every cell selection change for instant sync
    
    On Error Resume Next
    Application.ScreenUpdating = False
    Application.EnableEvents = False
    
    Dim formatoCol As Long
    formatoCol = 11 ' Column K = FORMATO
    
    ' Horario table spans columns A(1) through I(9): Name + 7 days + Hours
    Dim horarioLastCol As Long
    horarioLastCol = 9
    
    ' Obligaciones table spans columns A(1) through H(8): Name + 7 days
    Dim obligLastCol As Long
    obligLastCol = 8
    
    ' Find OBLIGACIONES header row
    Dim obligHdrRow As Long
    obligHdrRow = 0
    Dim searchR As Long
    For searchR = 1 To 200
        If InStr(1, Cells(searchR, 1).Value, "OBLIGACIONES", vbTextCompare) > 0 Then
            obligHdrRow = searchR + 1 ' Row with column headers
            Exit For
        End If
    Next searchR
    
    ' For each entry in FORMATO column (employees + LIBRE)
    Dim r As Long
    For r = 2 To 50
        Dim fmtLabel As String
        fmtLabel = Trim(Cells(r, formatoCol).Value)
        If fmtLabel = "" Then Exit For
        
        Dim bgClr As Long
        bgClr = Cells(r, formatoCol).Interior.Color
        
        Dim ftClr As Long
        ftClr = Cells(r, formatoCol).Font.Color
        
        Dim ftBold As Boolean
        ftBold = Cells(r, formatoCol).Font.Bold
        
        Dim ftItalic As Boolean
        ftItalic = Cells(r, formatoCol).Font.Italic
        
        ' Check if this is the LIBRE format entry
        If UCase(fmtLabel) = "LIBRE" Then
            ' Apply LIBRE format to all cells containing "LIBRE" in both tables
            Dim hR As Long
            For hR = 2 To 50
                If Trim(Cells(hR, 1).Value) = "" Then Exit For
                Dim hC As Long
                For hC = 2 To horarioLastCol
                    If UCase(Trim(Cells(hR, hC).Value)) = "LIBRE" Then
                        Cells(hR, hC).Interior.Color = bgClr
                        Cells(hR, hC).Font.Color = ftClr
                        Cells(hR, hC).Font.Bold = ftBold
                        Cells(hR, hC).Font.Italic = ftItalic
                    End If
                Next hC
            Next hR
        Else
            ' Employee: apply to ENTIRE row in Horario
            If Trim(Cells(r, 1).Value) = fmtLabel Then
                Dim c As Long
                For c = 1 To horarioLastCol
                    Cells(r, c).Interior.Color = bgClr
                    Cells(r, c).Font.Color = ftClr
                    Cells(r, c).Font.Bold = ftBold
                    Cells(r, c).Font.Italic = ftItalic
                Next c
            End If
            
            ' Employee: apply to ENTIRE row in Obligaciones
            If obligHdrRow > 0 Then
                Dim taskR As Long
                For taskR = obligHdrRow + 1 To obligHdrRow + 50
                    If Trim(Cells(taskR, 1).Value) = fmtLabel Then
                        Dim tc As Long
                        For tc = 1 To obligLastCol
                            Cells(taskR, tc).Interior.Color = bgClr
                            Cells(taskR, tc).Font.Color = ftClr
                            Cells(taskR, tc).Font.Bold = ftBold
                            Cells(taskR, tc).Font.Italic = ftItalic
                        Next tc
                        Exit For
                    End If
                    If Cells(taskR, 1).Value = "" Then Exit For
                Next taskR
            End If
        End If
    Next r
    
    Application.EnableEvents = True
    Application.ScreenUpdating = True
End Sub
'''

def create_template():
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "formato_template.xlsm")
    
    print("Creating Excel template with VBA macro...")
    print(f"Output: {template_path}")
    
    excel = None
    wb = None
    try:
        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        
        wb = excel.Workbooks.Add()
        ws = wb.Worksheets(1)
        ws.Name = "Horario"
        
        # Add VBA code to Sheet1 (Horario)
        vb_component = wb.VBProject.VBComponents(ws.CodeName)
        vb_component.CodeModule.AddFromString(VBA_CODE.strip())
        
        # Delete if exists
        if os.path.exists(template_path):
            os.remove(template_path)
        
        # Save as macro-enabled workbook (.xlsm)
        wb.SaveAs(template_path, 52)  # 52 = xlOpenXMLWorkbookMacroEnabled
        print("Template created successfully!")
        print("\nNow the export will produce .xlsm files with auto-propagating format.")
        
    except Exception as e:
        print(f"Error: {e}")
        print("\nIf you get a 'Programmatic access to Visual Basic Project is not trusted' error:")
        print("1. Open Excel")
        print("2. File > Options > Trust Center > Trust Center Settings")
        print("3. Macro Settings > Check 'Trust access to the VBA project object model'")
        print("4. Click OK and re-run this script")
        sys.exit(1)
    finally:
        if wb:
            try:
                wb.Close(False)
            except:
                pass
        if excel:
            try:
                excel.Quit()
            except:
                pass
            # Give Excel time to close
            time.sleep(1)

if __name__ == "__main__":
    create_template()
