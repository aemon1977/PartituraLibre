/* Lanzador de Partitura Libre para Windows (se compila en GitHub y va en el paquete completo).
 *
 * Abre el programa con el Python portable que lleva el propio paquete en runtime\, sin consola y sin
 * instalar ni tocar nada del sistema. Con --diagnostico, --reparar o --deshacer-actualizacion usa la
 * versión de consola de Python, espera y devuelve su código de salida.
 * Compilar:  rc /fo icono.res icono.rc && cl /O2 /utf-8 PartituraLibre.c icono.res user32.lib /link /SUBSYSTEM:WINDOWS
 */
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <wchar.h>

#define LARGO 32768

static int buscar_python(const wchar_t *dir, const wchar_t *nombre, wchar_t *ruta)
{
    wchar_t patron[LARGO];
    WIN32_FIND_DATAW d;
    HANDLE h;
    swprintf(patron, LARGO, L"%ls\\runtime\\python\\cpython-3.11*", dir);
    h = FindFirstFileW(patron, &d);
    if (h == INVALID_HANDLE_VALUE)
        return 0;
    do {
        if (d.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            swprintf(ruta, LARGO, L"%ls\\runtime\\python\\%ls\\%ls", dir, d.cFileName, nombre);
            if (GetFileAttributesW(ruta) != INVALID_FILE_ATTRIBUTES) {
                FindClose(h);
                return 1;
            }
        }
    } while (FindNextFileW(h, &d));
    FindClose(h);
    return 0;
}

int WINAPI wWinMain(HINSTANCE instancia, HINSTANCE previa, PWSTR argumentos, int mostrar)
{
    static wchar_t dir[LARGO], python[LARGO], app[LARGO], linea[2 * LARGO];
    STARTUPINFOW inicio = {sizeof(inicio)};
    PROCESS_INFORMATION proceso;
    DWORD codigo = 1, opciones = 0;
    wchar_t *barra;
    int consola = wcsstr(argumentos, L"--diagnostico") || wcsstr(argumentos, L"--reparar")
                  || wcsstr(argumentos, L"--deshacer-actualizacion");

    GetModuleFileNameW(NULL, dir, LARGO);
    barra = wcsrchr(dir, L'\\');
    if (barra)
        *barra = 0;
    if (!buscar_python(dir, consola ? L"python.exe" : L"pythonw.exe", python)) {
        MessageBoxW(NULL, L"No se encuentra el Python que acompaña al programa (carpeta «runtime»).\n\n"
                          L"Vuelve a descomprimir el paquete completo de Partitura Libre en una carpeta tuya.",
                    L"Partitura Libre", MB_ICONERROR);
        return 1;
    }
    swprintf(app, LARGO, L"%ls\\app", dir);
    SetEnvironmentVariableW(L"PYTHONPATH", app);
    SetEnvironmentVariableW(L"PYTHONHOME", NULL);
    SetEnvironmentVariableW(L"PYTHONSTARTUP", NULL);
    SetEnvironmentVariableW(L"VIRTUAL_ENV", NULL);
    SetEnvironmentVariableW(L"PYTHONNOUSERSITE", L"1");
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    swprintf(linea, 2 * LARGO, L"\"%ls\" -s -m partitura_libre.lanzar --si %ls", python, argumentos);
    if (consola) {   /* desde una terminal: se usa la suya; con doble clic, una consola nueva */
        inicio.dwFlags = STARTF_USESTDHANDLES;
        inicio.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
        inicio.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
        inicio.hStdError = GetStdHandle(STD_ERROR_HANDLE);
        if (!inicio.hStdOutput) {
            inicio.dwFlags = 0;
            opciones = CREATE_NEW_CONSOLE;
        }
    }
    if (!CreateProcessW(python, linea, NULL, NULL, consola, opciones, NULL, dir, &inicio, &proceso)) {
        MessageBoxW(NULL, L"No se pudo abrir Partitura Libre. Vuelve a descomprimir el paquete completo.",
                    L"Partitura Libre", MB_ICONERROR);
        return 1;
    }
    if (consola) {
        WaitForSingleObject(proceso.hProcess, INFINITE);
        GetExitCodeProcess(proceso.hProcess, &codigo);
    } else {
        codigo = 0;
    }
    CloseHandle(proceso.hProcess);
    CloseHandle(proceso.hThread);
    return (int)codigo;
}
